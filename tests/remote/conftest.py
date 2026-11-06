import time
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from cloudflare import AsyncCloudflare
from tenacity import retry, stop_after_delay, wait_exponential

from proxyflare.constants import WORKER_KEY_BYTES
from proxyflare.models.config import Config
from proxyflare.models.deployment import DeploymentConfig
from proxyflare.models.worker_result import WorkerRecord
from proxyflare.services.worker import WorkerService


@retry(stop=stop_after_delay(60), wait=wait_exponential(multiplier=1, min=4, max=10), reraise=True)
async def wait_for_worker(url: str) -> None:
    """Poll until the worker answers. Without a key it replies 401; 404 means not propagated yet."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code != 401:
        raise RuntimeError(f"Worker not ready: {response.status_code}")


@pytest.fixture(scope="session")
def config() -> Config:
    try:
        return Config()  # ty: ignore[missing-argument]
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
