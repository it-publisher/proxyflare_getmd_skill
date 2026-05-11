__all__ = ["ProxyflareError", "SubdomainMissingError"]


class ProxyflareError(Exception):
    """Base exception for all Proxyflare errors."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class SubdomainMissingError(ProxyflareError):
    """Raised when the Cloudflare account has no subdomain configured."""
