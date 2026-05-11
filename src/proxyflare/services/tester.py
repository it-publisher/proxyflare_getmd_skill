import httpx
from loguru import logger

from proxyflare.constants import DEFAULT_WORKER_TIMEOUT

__all__ = ["WorkerTester"]


class WorkerTester:
    """Service for testing deployed Cloudflare Workers."""

    def __init__(self, timeout: float = DEFAULT_WORKER_TIMEOUT) -> None:
        self.timeout = timeout

    def check_health(self, url: str) -> bool:
        """
        Check if the worker is reachable and responding.

        Returns True if reachable, False otherwise.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                client.get(url)
                return True
        except Exception as e:
            logger.debug(f"Health check failed for {url}: {e}")
            return False

    def test_proxy(self, worker_url: str, target_url: str) -> bool:
        """
        Verify that the worker correctly proxies a request to the target URL.

        Returns True if the proxy request succeeded (200 OK), False otherwise.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{worker_url}", params={"url": target_url})
                if resp.status_code == 200:
                    return True
                logger.warning(f"Proxy test returned {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"Proxy test failed: {e}")
            return False
