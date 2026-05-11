"""Typed application context and factory for CLI commands."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import typer
from cloudflare import AsyncCloudflare

from proxyflare.cli.console import err_console as _err_console
from proxyflare.models.config import Config
from proxyflare.services.worker import WorkerService

__all__ = ["AppContext", "get_app_context"]


@dataclass(frozen=True)
class AppContext:
    """Typed container for shared CLI dependencies."""

    config: Config
    client: AsyncCloudflare
    service: WorkerService


@asynccontextmanager
async def get_app_context() -> AsyncIterator[AppContext]:
    """Async context manager for dependency initialization.

    Ensures AsyncCloudflare is created within the running event loop.
    Raises typer.Exit(1) on configuration errors.
    """
    try:
        config = Config()  # type: ignore[call-arg]
    except Exception as e:
        _err_console.print(f"[bold red]Configuration error:[/bold red] {e}")
        _err_console.print(
            "[dim]Hint: Ensure PROXYFLARE_ACCOUNT_ID and PROXYFLARE_API_TOKEN "
            "are set in your environment or .env file.[/dim]"
        )
        raise typer.Exit(1) from e

    async with AsyncCloudflare(api_token=config.api_token.get_secret_value()) as client:
        service = WorkerService(client, config.account_id, config.worker_prefix)
        yield AppContext(config=config, client=client, service=service)
