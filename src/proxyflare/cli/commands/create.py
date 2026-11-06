import asyncio
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from proxyflare.cli.console import console, err_console
from proxyflare.cli.context import get_app_context
from proxyflare.cli.exceptions import ConfigError, WorkerError
from proxyflare.constants import (
    DEFAULT_DEPLOY_CONCURRENCY,
    WORKER_KEY_BYTES,
    WORKER_PROPAGATION_SECONDS,
    WORKER_TYPES,
    WorkerType,
)
from proxyflare.exceptions import ProxyflareError
from proxyflare.models.deployment import DeploymentConfig
from proxyflare.models.worker_result import WorkerRecord, WorkerResultFile
from proxyflare.paths import get_workers_file

if TYPE_CHECKING:
    from rich.progress import TaskID

    from proxyflare.cli.context import AppContext


async def _deploy_workers_parallel(
    ctx: "AppContext",
    script_content: str,
    worker_type: WorkerType,
    wasm_content: bytes | None,
    count: int,
    progress: Progress,
    task_id: "TaskID",
) -> list[WorkerRecord]:
    """
    Deploy multiple workers in parallel using asyncio.gather and a semaphore.

    Args:
        ctx: Application context containing the Cloudflare service.
        script_content: Source code of the worker.
        worker_type: Type of worker (rust/js).
        wasm_content: Optional WASM binary.
        count: Number of workers to deploy.
        progress: Rich progress bar instance.
        task_id: Rich task ID for progress tracking.

    Returns:
        A list of WorkerRecord objects for successful deployments.
    """
    sem = asyncio.Semaphore(DEFAULT_DEPLOY_CONCURRENCY)

    async def _deploy_one() -> WorkerRecord | None:
        name = ctx.service.generate_worker_name()
        key = secrets.token_urlsafe(WORKER_KEY_BYTES)
        async with sem:
            try:
                config = DeploymentConfig(
                    name=name,
                    script_content=script_content,
                    worker_type=worker_type,
                    key=key,
                    wasm_content=wasm_content,
                )
                url = await ctx.service.deploy_worker(config)
                progress.advance(task_id)
                return WorkerRecord(
                    name=name,
                    url=url,
                    type=worker_type,
                    created_at=time.time(),
                    key=key,
                )
            except Exception as e:
                # Log error but don't fail everything
                err_console.print(
                    f"[bold red]Error:[/bold red] Failed to create worker [bold]{name}[/bold]: {e}"
                )
                progress.advance(task_id)
                return None

    tasks = [_deploy_one() for _ in range(count)]
    settled = await asyncio.gather(*tasks)
    return [r for r in settled if r is not None]


async def _create_async(
    count: int,
    worker_type: str | None,
    result: Path,
) -> None:
    """
    Asynchronous implementation of the worker creation command.

    Args:
        count: Number of workers to create.
        worker_type: Optional override for the worker type.
        result: Path to save the deployment results.

    Raises:
        ConfigError: If configuration is invalid.
        WorkerError: If deployment fails.
    """
    # Checked before deploying, or new workers would end up with nowhere to be recorded
    try:
        existing_workers = WorkerResultFile.load_or_empty(result).root
    except ValueError as e:
        raise ConfigError(f"Workers file {result} is invalid, fix or remove it: {e}") from e

    async with get_app_context() as ctx:
        # Resolve worker type
        final_worker_type_str = worker_type or ctx.config.worker_type

        # Validate worker type
        if final_worker_type_str not in WORKER_TYPES:
            raise ConfigError(
                f"Invalid worker type '{final_worker_type_str}'. Must be 'js' or 'rust'."
            )

        final_worker_type: WorkerType = final_worker_type_str

        # Load Source
        try:
            script_content, wasm_content = ctx.service.get_worker_source(final_worker_type)
        except FileNotFoundError as e:
            raise WorkerError(str(e)) from e
        except Exception as e:
            raise WorkerError(f"Failed to load worker source: {e}") from e

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Ensure Subdomain + Create Workers
            task_subdomain = progress.add_task("Checking subdomain...", total=None)

            try:
                subdomain = await ctx.service.ensure_subdomain()
                progress.update(task_subdomain, completed=True, visible=False)
                console.print(
                    f"[green]✓[/green] Using subdomain: [bold]{subdomain}.workers.dev[/bold]"
                )

                task_create = progress.add_task(f"Creating {count} workers...", total=count)
                results_data = await _deploy_workers_parallel(
                    ctx,
                    script_content,
                    final_worker_type,
                    wasm_content,
                    count,
                    progress,
                    task_create,
                )

            except ProxyflareError:
                raise
            except Exception as e:
                raise WorkerError(
                    f"Could not complete deployment. Check your API token and account settings: {e}"
                ) from e

        if not results_data:
            raise WorkerError("No workers were created.")

        WorkerResultFile(root=[*existing_workers, *results_data]).save(result)
        console.print(
            f"\n[bold green]Successfully created {len(results_data)} workers![/bold green]"
        )
        console.print(f"Results saved to: [bold]{result}[/bold]")
        console.print(
            "[dim]New workers can answer with errors for about "
            f"{WORKER_PROPAGATION_SECONDS} seconds while they reach all Cloudflare locations.[/dim]"
        )

        failed_count = count - len(results_data)
        if failed_count:
            raise WorkerError(f"{failed_count} of {count} workers failed to deploy.")


def create(
    count: Annotated[int, typer.Option(min=1, help="Number of workers to create")] = 1,
    worker_type: Annotated[
        str | None,
        typer.Option("--type", help="Type of worker (js/rust). Defaults to config."),
    ] = None,
    result: Annotated[
        Path | None,
        typer.Option(help="Workers file to add to [default: in config directory]"),
    ] = None,
) -> None:
    """Deploy new Cloudflare proxy workers."""
    asyncio.run(_create_async(count, worker_type, result or get_workers_file()))
