from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from proxyflare.cli.console import console, err_console, print_error
from proxyflare.cli.context import get_app_context
from proxyflare.cli.exceptions import WorkerError

if TYPE_CHECKING:
    from proxyflare.cli.context import AppContext


async def _delete_worker_async(
    name: str | None,
    all_workers: bool,
    force: bool,
) -> None:
    async with get_app_context() as ctx:
        if all_workers:
            await _delete_all_workers(ctx, force)
        else:
            if name is None:
                raise WorkerError("Worker name is required when not using --all")
            await _delete_single_worker(ctx, name, force)


async def _delete_single_worker(ctx: AppContext, name: str, force: bool) -> None:
    if not force:
        if not Confirm.ask(f"Are you sure you want to delete worker [cyan]{name}[/cyan]?"):
            err_console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit(0)

    try:
        await ctx.service.delete_worker(name)
        console.print(f"[green]Successfully deleted worker: [bold]{name}[/bold][/green]")
    except ValueError as e:
        raise WorkerError(str(e)) from e
    except Exception as e:
        raise WorkerError(
            f"Failed to delete worker {name}. Check your API token and network connection."
        ) from e


async def _delete_all_workers(ctx: AppContext, force: bool) -> None:
    try:
        workers = await ctx.service.list_workers()
    except Exception as e:
        raise WorkerError(
            "Failed to list workers. Check your API token and network connection."
        ) from e

    if not workers:
        console.print("[yellow]No workers found to delete.[/yellow]")
        return

    console.print(
        f"Found [bold]{len(workers)}[/bold] worker(s) with prefix "
        f"[cyan]{ctx.service.worker_prefix}-[/cyan]:"
    )
    for w in workers:
        console.print(f"  • {w.get('id', 'Unknown')}")

    if not force:
        if not Confirm.ask(f"\nDelete all [bold]{len(workers)}[/bold] workers?"):
            err_console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit(0)

    deleted: list[str] = []
    failed: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Deleting {len(workers)} workers...", total=None)
        for w in workers:
            name = w.get("id", "Unknown")
            try:
                await ctx.service.delete_worker(name)
                deleted.append(name)
            except Exception:
                failed.append(name)
        progress.update(task, completed=True, visible=False)

    console.print(f"\n[bold green]Deleted {len(deleted)} worker(s).[/bold green]")
    if failed:
        for name in failed:
            print_error(f"Failed to delete {name}")
        print_error(f"Failed to delete {len(failed)} worker(s).")


def delete_worker(
    name: str | None = typer.Argument(None, help="Name of the worker to delete"),
    all_workers: bool = typer.Option(False, "--all", help="Delete all workers with current prefix"),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation"),
) -> None:
    """Remove a deployed worker or all workers with --all."""
    if not name and not all_workers:
        print_error("Provide a worker name or use --all to delete all workers.")
        raise typer.Exit(1)

    if name and all_workers:
        print_error("Cannot use both a worker name and --all together.")
        raise typer.Exit(1)

    asyncio.run(_delete_worker_async(name, all_workers, force))
