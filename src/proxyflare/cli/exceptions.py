from proxyflare.exceptions import ProxyflareError

__all__ = [
    "APIError",
    "BuildError",
    "ConfigError",
    "ProxyflareError",
    "WorkerError",
]


class ConfigError(ProxyflareError):
    """Raised when there is a configuration error."""


class WorkerError(ProxyflareError):
    """Raised when a worker operation fails."""


class BuildError(ProxyflareError):
    """Raised when a worker build fails."""


class APIError(ProxyflareError):
    """Raised when an external API call fails."""
