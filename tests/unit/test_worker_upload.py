"""Deploys through the real Cloudflare SDK, faking only the network, to catch SDK format changes."""

import httpx
import pytest
import respx
from cloudflare import AsyncCloudflare
from tenacity import wait_none

from proxyflare.models.deployment import DeploymentConfig
from proxyflare.services.worker import WorkerService

API = "https://api.cloudflare.com/client/v4/accounts/test-account/workers"


def api_response(result: dict) -> httpx.Response:
    return httpx.Response(
        200, json={"success": True, "errors": [], "messages": [], "result": result}
    )


@pytest.fixture
def cloudflare_api():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{API}/subdomain").mock(return_value=api_response({"subdomain": "test-sub"}))
        mock.post(f"{API}/scripts/test-worker/subdomain").mock(
            return_value=api_response({"enabled": True})
        )
        yield mock.put(f"{API}/scripts/test-worker").mock(
            return_value=api_response({"id": "test-worker"})
        )


@pytest.mark.parametrize(
    ("worker_type", "wasm_content", "expected_parts"),
    [
        ("js", None, [b'name="worker.js"']),
        ("rust", b"wasm-bytes", [b'name="worker.js"', b'name="index_bg.wasm"', b"wasm-bytes"]),
    ],
)
async def test_deploy_uploads_files_and_key(
    cloudflare_api, monkeypatch, worker_type, wasm_content, expected_parts
):
    monkeypatch.setattr(WorkerService.deploy_worker.retry, "wait", wait_none())

    async with AsyncCloudflare(api_token="test-token") as client:  # noqa: S106
        url = await WorkerService(client, "test-account").deploy_worker(
            DeploymentConfig(
                name="test-worker",
                script_content="export default {}",
                worker_type=worker_type,
                key="secret-key",
                wasm_content=wasm_content,
            )
        )

    assert url == "https://test-worker.test-sub.workers.dev"
    body = cloudflare_api.calls.last.request.content
    assert b"export default {}" in body
    assert b"secret-key" in body
    assert b'"main_module"' in body
    for part in expected_parts:
        assert part in body
