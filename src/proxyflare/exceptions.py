__all__ = ["FetchError", "ProxyflareError", "SubdomainMissingError"]


class ProxyflareError(Exception):
    """Base exception for all Proxyflare errors."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class FetchError(ProxyflareError):
    """Raised when a page could not be downloaded through the workers."""


class SubdomainMissingError(ProxyflareError):
    """Raised when the Cloudflare account has no subdomain configured."""
