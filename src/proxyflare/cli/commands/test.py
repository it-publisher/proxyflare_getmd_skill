from itertools import cycle
from pathlib import Path
from typing import Annotated

import httpx
import typer

from proxyflare.cli.console import console, print_error, print_success, print_warning
from proxyflare.cli.exceptions import WorkerError
from proxyflare.client import ProxyflareTransport, ProxyflareWorkersManager
from proxyflare.models.worker_result import WorkerRecord
from proxyflare.paths import get_workers_file

RESPONSE_PREVIEW_LENGTH = 200


def _print_response(response: httpx.Response) -> None:
    status_style = "green" if response.is_success else "red"
    console.print(f"Status: [{status_style}]{response.status_code}[/{status_style}]")
    # markup=False: the body is arbitrary text, and square brackets in it would break Rich
    console.print("Response:", response.text[:RESPONSE_PREVIEW_LENGTH], markup=False)


def _check_worker(worker: WorkerRecord, url: str, timeout: float) -> bool:
    """Make one request through the worker and report whether it succeeded."""
    transport = ProxyflareTransport(manager=ProxyflareWorkersManager([worker]))
    try:
        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.get(url)
    except httpx.ConnectError:
        print_error(
            "Could not connect to worker. Check that the worker is deployed and accessible."
        )
        return False
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        print_error(f"Request failed: {e}")
        return False

    _print_response(response)
    return response.is_success


def test_workers(
    url: Annotated[
        str, typer.Option("--url", "-u", help="Target URL to test")
    ] = "https://httpbin.org/ip",
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", min=1, help="Number of requests [default: one per worker]"),
    ] = None,
    workers_file: Annotated[
        Path | None,
        typer.Option("--workers-file", "-f", help="Workers file [default: in config directory]"),
    ] = None,
    timeout: Annotated[float, typer.Option("--timeout", help="Timeout for each request")] = 10.0,
) -> None:
    """
    Test the proxying capabilities of deployed workers.

    Goes through the workers in turn, so by default each one gets exactly one request.
    """
    path = workers_file or get_workers_file()
    try:
        workers = ProxyflareWorkersManager(path).workers
    except FileNotFoundError:
        print_error(f"Workers file not found: [bold]{path}[/bold]")
        print_warning("Run [bold]proxyflare create[/bold] first to deploy workers.")
        raise typer.Exit(1) from None
    except ValueError as e:
        raise WorkerError(f"Failed to load workers file: {e}") from e

    print_success(f"Loaded {len(workers)} workers.")
    console.print(f"Testing against target: [cyan]{url}[/cyan]")

    request_count = limit or len(workers)
    failed_count = 0
    for number, worker in zip(range(1, request_count + 1), cycle(workers), strict=False):
        console.print(f"\n[bold]Request {number}/{request_count}[/bold] via {worker.name}")
        if not _check_worker(worker, url, timeout):
            failed_count += 1

    if failed_count:
        raise WorkerError(f"{failed_count} of {request_count} test requests failed.")
    print_success("\nTest complete.")
