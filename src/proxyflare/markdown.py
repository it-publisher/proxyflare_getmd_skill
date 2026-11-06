"""Downloads a page through the workers and turns it into a Markdown document."""

import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
import trafilatura

from proxyflare.client import ProxyflareTransport, ProxyflareWorkersManager
from proxyflare.constants import WORKER_ERROR_HEADER
from proxyflare.exceptions import FetchError
from proxyflare.models.worker_result import WorkerRecord

__all__ = [
    "Article",
    "extract_article",
    "fetch_html",
    "format_document",
    "save_document",
    "slugify",
]

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 25.0
# A file name is limited to 255 bytes. The margin leaves room for a suffix and the extension.
MAX_SLUG_BYTES = 200
FALLBACK_SLUG = "article"
HEADING_SEARCH_LINES = 5

# trafilatura sometimes takes one nested block for the whole article and silently drops the rest.
# Below this share of the page's text the result is treated as such a mistake. A short article
# surrounded by navigation can legitimately be a small share, so tiny pages are not checked.
MIN_EXTRACTED_SHARE = 0.1
MIN_PAGE_CHARS_FOR_SHARE_CHECK = 5000

# Sites often block clients that don't look like a browser
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass(frozen=True)
class Article:
    title: str
    content: str
    has_formatting: bool = True


def slugify(text: str) -> str:
    """Turn arbitrary text into a safe, non-empty file name."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    # Cut by bytes, not characters: Cyrillic takes 2 bytes per character
    slug = slug.encode()[:MAX_SLUG_BYTES].decode(errors="ignore").rstrip("-")
    return slug or FALLBACK_SLUG


def _request_page(url: str, worker: WorkerRecord) -> httpx.Response:
    manager = ProxyflareWorkersManager(source=[worker])
    with httpx.Client(
        transport=ProxyflareTransport(manager),
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=BROWSER_HEADERS,
    ) as client:
        return client.get(url)


def _is_worker_failure(response: httpx.Response) -> bool:
    """Tell whether another worker might do better than this one."""
    if response.status_code == 429 or response.status_code >= 500:
        return True
    if WORKER_ERROR_HEADER in response.headers:
        return True
    # Site responses always pass through a worker, which adds this header. Without it the response
    # came from Cloudflare itself, like a 404 for a deleted worker, and says nothing about the site.
    return "access-control-allow-origin" not in response.headers


def _decode_body(response: httpx.Response) -> str | bytes:
    # Without a charset in the header httpx assumes UTF-8 and garbles e.g. windows-1251.
    # Given bytes, trafilatura detects the encoding on its own.
    return response.text if response.charset_encoding else response.content


def fetch_html(
    url: str,
    workers: list[WorkerRecord],
    on_attempt_failed: Callable[[str], None] = lambda _: None,
) -> str | bytes:
    """
    Download a page, moving on to another worker when one fails.

    An error from the site itself, like 403 or 404, won't change with a retry and is raised at once.

    Raises:
        FetchError: If the site returned an error or every attempt failed.
    """
    attempts = secrets.SystemRandom().sample(workers, k=min(MAX_ATTEMPTS, len(workers)))

    for number, worker in enumerate(attempts, start=1):
        try:
            response = _request_page(url, worker)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            on_attempt_failed(f"Attempt {number}/{len(attempts)}: {str(e) or type(e).__name__}")
            continue

        if _is_worker_failure(response):
            on_attempt_failed(f"Attempt {number}/{len(attempts)}: HTTP {response.status_code}")
            continue

        if not response.is_success:
            raise FetchError(f"The site responded with HTTP {response.status_code}")

        return _decode_body(response)

    raise FetchError(f"Could not download the page: all {len(attempts)} attempts failed")


def _lost_most_of_the_page(content: str, page_text: str) -> bool:
    if len(page_text) < MIN_PAGE_CHARS_FOR_SHARE_CHECK:
        return False
    return len(content) < len(page_text) * MIN_EXTRACTED_SHARE


def extract_article(html: str | bytes) -> Article | None:
    """Extract the title and the main text. Returns None if the page has no article."""
    content = trafilatura.extract(
        html, include_comments=False, include_tables=True, output_format="markdown"
    )
    if not content:
        return None

    # Declared to take str, but it passes the input to load_html, which handles bytes as well
    metadata = trafilatura.metadata.extract_metadata(html)  # ty: ignore[invalid-argument-type]
    title = (
        metadata.title
        if metadata and metadata.title
        else f"article_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    if _lost_most_of_the_page(content, trafilatura.html2txt(html)):
        _, plain_text, _ = trafilatura.baseline(html)
        return Article(title=title, content=plain_text, has_formatting=False)

    return Article(title=title, content=content)


def format_document(article: Article, url: str) -> str:
    """Build the final Markdown: metadata, heading and text."""
    single_line_title = " ".join(article.title.split())
    # The text often opens with the page's own H1, sometimes after a line or two of other text,
    # and a second heading would duplicate it
    opening_lines = article.content.lstrip().splitlines()[:HEADING_SEARCH_LINES]
    has_heading = any(line.startswith("# ") for line in opening_lines)
    heading = "" if has_heading else f"# {single_line_title}\n\n"
    # A JSON string is a valid YAML string, so quotes and colons in the title are safe
    return (
        "---\n"
        f"title: {json.dumps(single_line_title, ensure_ascii=False)}\n"
        f"source: {json.dumps(url, ensure_ascii=False)}\n"
        f"saved: {date.today().isoformat()}\n"
        "---\n\n"
        f"{heading}{article.content}\n"
    )


def save_document(title: str, document: str, output_dir: Path) -> Path:
    """
    Save the document under a name derived from the title, never overwriting an existing file.

    Raises:
        OSError: If the file can't be written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)

    number = 1
    while True:
        suffix = "" if number == 1 else f"-{number}"
        path = output_dir / f"{slug}{suffix}.md"
        try:
            # Mode "x" fails if the file exists, so two runs at once can't overwrite each other
            with path.open("x", encoding="utf-8") as file:
                file.write(document)
        except FileExistsError:
            number += 1
            continue
        return path
