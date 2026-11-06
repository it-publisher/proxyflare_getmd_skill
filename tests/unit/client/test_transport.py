from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from proxyflare.client import (
    AsyncProxyflareTransport,
    ProxyflareTransport,
    ProxyflareWorkersManager,
)
from proxyflare.models.worker_result import WorkerRecord


@pytest.fixture
def mock_manager():
    manager = Mock(spec=ProxyflareWorkersManager)
    manager.get_worker.return_value = WorkerRecord(
        name="w", url="https://worker.dev", type="js", created_at=1.0, key="test-key"
    )
    return manager


def test_transport_sync_request(mock_manager):
    transport = ProxyflareTransport(manager=mock_manager)
    # Mock internal transport
    transport._pool = Mock(spec=httpx.HTTPTransport)
    transport._pool.handle_request.return_value = httpx.Response(200)

    request = httpx.Request("GET", "https://httpbin.org/ip")
    response = transport.handle_request(request)

    assert response.status_code == 200
    mock_manager.get_worker.assert_called_once()

    # Verify request rewriting
    call_args = transport._pool.handle_request.call_args
    sent_request = call_args[0][0]

    expected_url = "https://worker.dev?url=https%3A%2F%2Fhttpbin.org%2Fip"
    assert str(sent_request.url) == expected_url
    assert sent_request.headers["Host"] == "worker.dev"
    assert sent_request.headers["X-Proxyflare-Key"] == "test-key"


def test_transport_context_manager(mock_manager):
    transport = ProxyflareTransport(manager=mock_manager)
    transport._pool = MagicMock(spec=httpx.HTTPTransport)

    with transport as t:
        assert t is transport
        transport._pool.__enter__.assert_called_once()

    transport._pool.__exit__.assert_called_once()


def test_transport_close(mock_manager):
    transport = ProxyflareTransport(manager=mock_manager)
    transport._pool = Mock(spec=httpx.HTTPTransport)

    transport.close()
    transport._pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_transport_async_request(mock_manager):
    transport = AsyncProxyflareTransport(manager=mock_manager)
    # Mock internal transport
    transport._pool = Mock(spec=httpx.AsyncHTTPTransport)

    transport._pool.handle_async_request = AsyncMock(return_value=httpx.Response(200))

    request = httpx.Request("GET", "https://httpbin.org/ip")
    response = await transport.handle_async_request(request)

    assert response.status_code == 200
    mock_manager.get_worker.assert_called_once()

    call_args = transport._pool.handle_async_request.call_args
    sent_request = call_args[0][0]

    expected_url = "https://worker.dev?url=https%3A%2F%2Fhttpbin.org%2Fip"
    assert str(sent_request.url) == expected_url
    assert sent_request.headers["Host"] == "worker.dev"
    assert sent_request.headers["X-Proxyflare-Key"] == "test-key"


@pytest.mark.asyncio
async def test_async_transport_context_manager(mock_manager):
    transport = AsyncProxyflareTransport(manager=mock_manager)
    transport._pool = Mock(spec=httpx.AsyncHTTPTransport)

    # Mock async context methods
    # AsyncMock is awaitable and returns the return_value
    transport._pool.__aenter__ = AsyncMock(return_value=transport._pool)
    transport._pool.__aexit__ = AsyncMock(return_value=None)

    async with transport as t:
        assert t is transport
        transport._pool.__aenter__.assert_called_once()

    transport._pool.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_async_transport_aclose(mock_manager):
    transport = AsyncProxyflareTransport(manager=mock_manager)
    transport._pool = Mock(spec=httpx.AsyncHTTPTransport)

    transport._pool.aclose = AsyncMock(return_value=None)

    await transport.aclose()
    transport._pool.aclose.assert_called_once()
