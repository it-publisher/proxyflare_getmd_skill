from typing import Self

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from proxyflare.constants import DEFAULT_WORKER_TYPE, WorkerType
from proxyflare.paths import get_env_file

__all__ = ["Config"]


class Config(BaseSettings):
    """
    Configuration settings for Proxyflare.

    Loaded from environment variables with 'PROXYFLARE_' prefix or from the .env file
    in the config directory. Environment variables win.
    """

    account_id: str
    """Cloudflare account ID."""

    api_token: SecretStr
    """Cloudflare API token."""

    worker_type: WorkerType = DEFAULT_WORKER_TYPE
    """Default worker type to create if not specified."""

    worker_prefix: str = "proxyflare"
    """Prefix for worker names to isolate resources."""

    model_config = SettingsConfigDict(
        env_prefix="PROXYFLARE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def load(cls) -> Self:
        """Load the configuration from the environment and the config directory."""
        return cls(_env_file=get_env_file())
