"""Runs each worker type through `wrangler dev` next to a local upstream server."""

import gzip
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from proxyflare.constants import COMPATIBILITY_DATE, WORKER_KEY_BINDING, WORKER_KEY_HEADER

WRANGLER_PACKAGE = "wrangler@4.90.0"
WORKER_START_TIMEOUT_SECONDS = 90
TEST_KEY = "contract-test-key"
BINARY_BODY = bytes(range(256))
ARTICLE_TEXT = "Съешь же ещё этих мягких французских булок, да выпей чаю. " * 12
ARTICLE_HTML = (
    "<html><head><title>Заголовок статьи</title></head><body><article>"
    f"<h1>Заголовок статьи</h1><p>{ARTICLE_TEXT}</p><p>{ARTICLE_TEXT}</p>"
    "</article></body></html>"
)

WORKERS_DIR = Path(__file__).parents[2] / "src" / "proxyflare" / "workers"
WORKER_ENTRY_POINTS = {
    "js": WORKERS_DIR / "js" / "worker.js",
    "rust": WORKERS_DIR / "rust" / "build" / "index.js",
}


@dataclass
class Upstream:
    url: str
    requests: list[dict] = field(default_factory=list)


class UpstreamHandler(BaseHTTPRequestHandler):
    server_version = "upstream"
    # HTTP/1.0 closes the connection after each response. Following a redirect, workerd could then
    # pick the closing connection and fail with "Network connection lost", which real sites avoid.
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        """Keep test output clean."""

    def send(self, status: int, body: bytes = b"", headers: tuple = ()) -> None:
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        if status not in (204, 304):
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def handle_any_method(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        echo = {
            "method": self.command,
            "path": self.path,
            "headers": {name.lower(): value for name, value in self.headers.items()},
            "body": self.rfile.read(length).decode("latin-1"),
        }
        self.server.upstream.requests.append(echo)
        self.route(echo)

    def route(self, echo: dict) -> None:
        route = self.path.split("?")[0]
        if route.startswith("/status/"):
            self.send(int(route.removeprefix("/status/")), headers=(("X-Upstream", "yes"),))
        elif route == "/redirect":
            self.send(302, headers=(("Location", "/echo?from=redirect"),))
        elif route == "/cookies":
            self.send(200, headers=(("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")))
        elif route == "/gzip":
            self.send(200, gzip.compress(b"compressed text"), (("Content-Encoding", "gzip"),))
        elif route == "/article":
            content_type = (("Content-Type", "text/html; charset=utf-8"),)
            self.send(200, ARTICLE_HTML.encode(), content_type)
        elif route == "/article-1251":
            self.send(200, ARTICLE_HTML.encode("cp1251"), (("Content-Type", "text/html"),))
        elif route == "/binary":
            self.send(200, BINARY_BODY, (("Content-Type", "application/octet-stream"),))
        else:
            self.send(200, json.dumps(echo).encode(), (("Content-Type", "application/json"),))

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = handle_any_method  # noqa: N815


@pytest.fixture(scope="session")
def upstream() -> Generator[Upstream, None, None]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    server.upstream = Upstream(url=f"http://127.0.0.1:{server.server_port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.upstream
    server.shutdown()


@pytest.fixture(autouse=True)
def clean_upstream_log(upstream: Upstream) -> None:
    upstream.requests.clear()


def get_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def write_wrangler_config(worker_type: str, directory: Path) -> Path:
    """Mirror what `pf create` uploads: the same files and compatibility date, no custom build."""
    config = directory / "wrangler.toml"
    config.write_text(
        f'name = "proxyflare-contract-{worker_type}"\n'
        f'main = "{WORKER_ENTRY_POINTS[worker_type]}"\n'
        f'compatibility_date = "{COMPATIBILITY_DATE}"\n'
    )
    return config


def wait_until_ready(url: str, log_file: Path) -> None:
    deadline = time.monotonic() + WORKER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=2)
            return
        except httpx.TransportError:
            time.sleep(0.5)
    raise RuntimeError(f"Worker didn't start at {url}:\n{log_file.read_text()}")


@pytest.fixture(scope="session", params=["js", "rust"])
def worker_url(request: pytest.FixtureRequest, tmp_path_factory) -> Generator[str, None, None]:
    worker_type = request.param
    if not shutil.which("npx"):
        pytest.fail("Contract tests need Node.js")
    if not WORKER_ENTRY_POINTS[worker_type].exists():
        message = f"{worker_type} worker is not built: python src/proxyflare/scripts/build_rust.py"
        if os.environ.get("REQUIRE_RUST_BUILD"):
            pytest.fail(message)
        pytest.skip(message)

    directory = tmp_path_factory.mktemp(worker_type)
    port = get_free_port()
    log_file = directory / "wrangler.log"
    command = [
        "npx",
        "--yes",
        WRANGLER_PACKAGE,
        "dev",
        "--config",
        str(write_wrangler_config(worker_type, directory)),
        "--ip",
        "127.0.0.1",
        "--port",
        str(port),
        "--var",
        f"{WORKER_KEY_BINDING}:{TEST_KEY}",
    ]
    env = {name: value for name, value in os.environ.items() if not name.startswith("CLOUDFLARE_")}
    env["WRANGLER_SEND_METRICS"] = "false"

    with log_file.open("w") as log:
        process = subprocess.Popen(
            command, cwd=directory, env=env, stdout=log, stderr=log, start_new_session=True
        )
    url = f"http://127.0.0.1:{port}"
    try:
        wait_until_ready(url, log_file)
        yield url
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)


@pytest.fixture
def client(worker_url: str) -> Generator[httpx.Client, None, None]:
    """A client authorized for the worker under test."""
    with httpx.Client(
        base_url=worker_url, headers={WORKER_KEY_HEADER: TEST_KEY}, timeout=20
    ) as authorized_client:
        yield authorized_client
