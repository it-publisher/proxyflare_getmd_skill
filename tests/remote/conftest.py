import asyncio
import time
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from cloudflare import AsyncCloudflare

from proxyflare.constants import WORKER_KEY_BYTES
from proxyflare.models.config import Config
from proxyflare.models.deployment import DeploymentConfig
from proxyflare.models.worker_result import WorkerRecord
from proxyflare.services.worker import WorkerService

STABLE_RESPONSES_REQUIRED = 20
WORKER_READY_TIMEOUT_SECONDS = 120


async def wait_for_worker(url: str) -> None:
    """
    Wait until the worker answers steadily. Without a key it replies 401.

    For about 15 seconds after a deploy, Cloudflare locations answer differently, mixing 401 with
    404 and 500. Each poll opens a new connection, because a reused one stays at one location.
    """
    deadline = time.monotonic() + WORKER_READY_TIMEOUT_SECONDS
    stable_responses = 0
    while stable_responses < STABLE_RESPONSES_REQUIRED:
        if time.monotonic() > deadline:
            raise RuntimeError(f"Worker didn't become ready in {WORKER_READY_TIMEOUT_SECONDS}s")
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        stable_responses = stable_responses + 1 if response.status_code == 401 else 0
        await asyncio.sleep(1)


@pytest.fixture(autouse=True)
def isolated_config_dir() -> None:
    """Overrides the isolation from tests/conftest.py: these tests need the real configuration."""


@pytest.fixture(scope="session")
def config() -> Config:
    try:
        return Config.load()
    except Exception as e:
        pytest.skip(f"Configuration not valid: {e}")


@pytest.fixture(params=["js", "rust"])
async def deployed_worker(request, config: Config) -> AsyncGenerator[WorkerRecord, None]:
    """Deploy a real worker, yield its record and delete it afterwards."""
    worker_type = request.param
    async with AsyncCloudflare(api_token=config.api_token.get_secret_value()) as client:
        service = WorkerService(client, config.account_id)
        script_content, wasm_content = service.get_worker_source(worker_type)
        name = f"proxyflare-e2e-{worker_type}-{uuid.uuid4().hex[:8]}"
        key = uuid.uuid4().hex * (WORKER_KEY_BYTES // 16)

        try:
            url = await service.deploy_worker(
                DeploymentConfig(
                    name=name,
                    script_content=script_content,
                    worker_type=worker_type,
                    key=key,
                    wasm_content=wasm_content,
                )
            )
            await wait_for_worker(url)
            yield WorkerRecord(
                name=name, url=url, type=worker_type, created_at=time.time(), key=key
            )
        finally:
            await service.delete_worker(name)
