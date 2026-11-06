import asyncio
import statistics
import time

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from proxyflare.constants import WORKER_KEY_HEADER

app = typer.Typer()
console = Console()


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[int, float]:
    start = time.perf_counter()
    try:
        response = await client.get(url)
        duration = (time.perf_counter() - start) * 1000  # ms
        return response.status_code, duration
    except httpx.RequestError:
        duration = (time.perf_counter() - start) * 1000  # ms
        return 0, duration


async def run_benchmark(
    worker_url: str, key: str, target_url: str, concurrency: int, total_requests: int
) -> None:
    full_url = f"{worker_url}/?url={target_url}"
    console.print(f"[bold blue]Starting benchmark against:[/bold blue] {full_url}")
    console.print(f"[bold]Concurrency:[/bold] {concurrency}")
    console.print(f"[bold]Total Requests:[/bold] {total_requests}")

    latencies: list[float] = []
    status_codes: dict[int, int] = {}

    start_time = time.perf_counter()

    async with httpx.AsyncClient(headers={WORKER_KEY_HEADER: key}) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Running requests...", total=total_requests)

            sem = asyncio.Semaphore(concurrency)

            async def bounded_fetch() -> tuple[int, float]:
                async with sem:
                    result = await fetch(client, full_url)
                    progress.advance(task_id)
                    return result

            tasks = [bounded_fetch() for _ in range(total_requests)]
            results = await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time

    for code, duration in results:
        latencies.append(duration)
        status_codes[code] = status_codes.get(code, 0) + 1

    # Statistics
    if total_time > 0:
        rps = total_requests / total_time
    else:
        rps = 0

    avg_latency = statistics.mean(latencies) if latencies else 0
    p50 = statistics.median(latencies) if latencies else 0
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else 0
    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else 0
    max_latency = max(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0

    # Output Table
    table = Table(title="Benchmark Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Total Time", f"{total_time:.2f} s")
    table.add_row("Requests per Second (RPS)", f"{rps:.2f}")
    table.add_row("Total Requests", str(total_requests))
    table.add_row("Successful (200 OK)", str(status_codes.get(200, 0)))
    table.add_row(
        "Errors (non-200)", str(sum(cnt for code, cnt in status_codes.items() if code != 200))
    )
    table.add_row("Latency (min)", f"{min_latency:.2f} ms")
    table.add_row("Latency (avg)", f"{avg_latency:.2f} ms")
    table.add_row("Latency (p50)", f"{p50:.2f} ms")
    table.add_row("Latency (p95)", f"{p95:.2f} ms")
    table.add_row("Latency (p99)", f"{p99:.2f} ms")
    table.add_row("Latency (max)", f"{max_latency:.2f} ms")

    console.print(table)


@app.command()
def main(
    worker_url: str = typer.Option("http://localhost:8787", help="URL of the worker"),
    key: str = typer.Option(..., envvar="PROXYFLARE_WORKER_KEY", help="Key of the worker"),
    target_url: str = typer.Option("https://httpbin.org/get", help="Target URL to proxy"),
    concurrency: int = typer.Option(50, help="Number of concurrent requests"),
    requests: int = typer.Option(1000, help="Total number of requests to make"),
) -> None:
    """
    Run a benchmark against the Proxyflare worker.
    """
    try:
        asyncio.run(run_benchmark(worker_url, key, target_url, concurrency, requests))
    except KeyboardInterrupt:
        console.print("[red]Benchmark interrupted[/red]")


if __name__ == "__main__":
    app()
