from pathlib import Path
from typing import Annotated

import httpx
import typer

from proxyflare.cli.console import console, print_warning
from proxyflare.cli.exceptions import ConfigError, WorkerError
from proxyflare.client import ProxyflareWorkersManager
from proxyflare.markdown import extract_article, fetch_html, format_document, save_document
from proxyflare.models.worker_result import WorkerRecord
from proxyflare.paths import get_workers_file


def _validate_url(url: str) -> None:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as e:
        raise typer.BadParameter(str(e), param_hint="URL") from e
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise typer.BadParameter("must start with http:// or https://", param_hint="URL")


def _load_workers(path: Path) -> list[WorkerRecord]:
    try:
        return ProxyflareWorkersManager(path).workers
    except FileNotFoundError as e:
        raise ConfigError(f"Workers file not found: {path}. Run `pf create` first.") from e
    except ValueError as e:
        raise ConfigError(f"Failed to load workers file: {e}") from e


def md(
    url: Annotated[str, typer.Argument(help="URL of the article, quote it in the shell")],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Directory to save the file to")
    ] = Path("articles"),
    workers_file: Annotated[
        Path | None,
        typer.Option("--workers-file", help="Workers file [default: in config directory]"),
    ] = None,
) -> None:
    """Download an article through the workers and save it as Markdown."""
    _validate_url(url)
    workers = _load_workers(workers_file or get_workers_file())

    html = fetch_html(url, workers, on_attempt_failed=print_warning)

    article = extract_article(html)
    if article is None:
        raise WorkerError("No article found on the page.")
    if not article.has_formatting:
        print_warning(
            "Automatic extraction lost most of the page, "
            "so the whole text was saved without formatting. It may include menus and footers."
        )

    try:
        saved_path = save_document(article.title, format_document(article, url), output)
    except OSError as e:
        raise WorkerError(f"Could not save the file: {e}") from e

    # Plain output with no wrapping: this line is meant to be usable by scripts
    console.print(str(saved_path), markup=False, highlight=False, soft_wrap=True)
