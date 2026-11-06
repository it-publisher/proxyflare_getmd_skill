"""Checks against real Cloudflare workers. Costs nothing, but needs a configured account."""

import httpx
import pytest

from proxyflare.client import AsyncProxyflareTransport, ProxyflareWorkersManager

pytestmark = pytest.mark.remote

TARGET = "https://httpbin.org"


async def test_request_without_key_is_rejected(deployed_worker):
    async with httpx.AsyncClient() as client:
        response = await client.get(deployed_worker.url, params={"url": f"{TARGET}/get"})
    assert response.status_code == 401


async def test_client_library_proxies_requests(deployed_worker):
    transport = AsyncProxyflareTransport(ProxyflareWorkersManager([deployed_worker]))
    async with httpx.AsyncClient(transport=transport, timeout=30) as client:
        get_response = await client.get(f"{TARGET}/get?a=1")
        post_response = await client.post(f"{TARGET}/post", json={"test": "data"})

    assert get_response.status_code == 200
    assert get_response.json()["args"] == {"a": "1"}
    assert "X-Proxyflare-Key" not in get_response.json()["headers"]
    assert post_response.json()["json"] == {"test": "data"}
