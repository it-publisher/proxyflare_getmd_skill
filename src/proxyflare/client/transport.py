import types
from typing import TYPE_CHECKING

import httpx

from proxyflare.constants import WORKER_KEY_HEADER

if TYPE_CHECKING:
    from .manager import ProxyflareWorkersManager

__all__ = ["AsyncProxyflareTransport", "ProxyflareTransport"]


def route_through_worker(request: httpx.Request, manager: "ProxyflareWorkersManager") -> None:
    """Rewrite the request in place, so it goes to a worker with the original URL as its target."""
    worker = manager.get_worker()
    proxied_url = httpx.URL(worker.url).copy_with(params={"url": str(request.url)})

    request.url = proxied_url
    request.headers["Host"] = proxied_url.netloc.decode()
    request.headers[WORKER_KEY_HEADER] = worker.key


class ProxyflareTransport(httpx.BaseTransport):
    """
    Synchronous transport that routes requests through Proxyflare workers.
    """

    def __init__(
        self,
        manager: "ProxyflareWorkersManager",
        verify: bool = True,
        cert: tuple | None = None,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits | None = None,
        trust_env: bool = True,
        retries: int = 0,
    ) -> None:
        self.manager = manager

        if limits is None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

        # Initialize internal transport to make the actual calls to workers
        self._pool = httpx.HTTPTransport(
            verify=verify,
            cert=cert,
            http1=http1,
            http2=http2,
            limits=limits,
            trust_env=trust_env,
            retries=retries,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        route_through_worker(request, self.manager)
        return self._pool.handle_request(request)

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> "ProxyflareTransport":
        self._pool.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: types.TracebackType | None = None,
    ) -> None:
        self._pool.__exit__(exc_type, exc_value, traceback)


class AsyncProxyflareTransport(httpx.AsyncBaseTransport):
    """
    Asynchronous transport that routes requests through Proxyflare workers.
    """

    def __init__(
        self,
        manager: "ProxyflareWorkersManager",
        verify: bool = True,
        cert: tuple | None = None,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits | None = None,
        trust_env: bool = True,
        retries: int = 0,
    ) -> None:
        self.manager = manager

        if limits is None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

        self._pool = httpx.AsyncHTTPTransport(
            verify=verify,
            cert=cert,
            http1=http1,
            http2=http2,
            limits=limits,
            trust_env=trust_env,
            retries=retries,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        route_through_worker(request, self.manager)
        return await self._pool.handle_async_request(request)

    async def aclose(self) -> None:
        await self._pool.aclose()

    async def __aenter__(self) -> "AsyncProxyflareTransport":
        await self._pool.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: types.TracebackType | None = None,
    ) -> None:
        await self._pool.__aexit__(exc_type, exc_value, traceback)
