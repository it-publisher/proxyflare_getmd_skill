"""The contract from docs/worker-contract.md, checked identically for every worker type."""

import re

import httpx
import pytest
from typer.testing import CliRunner

from proxyflare.cli.app import app
from proxyflare.client import ProxyflareTransport, ProxyflareWorkersManager
from proxyflare.constants import WORKER_KEY_HEADER
from proxyflare.exceptions import FetchError
from proxyflare.models.worker_result import WorkerRecord, WorkerResultFile
from tests.contract.conftest import BINARY_BODY, TEST_KEY

pytestmark = pytest.mark.contract

ERROR_HEADER = "X-Proxyflare-Error"
CORS_ORIGIN_HEADER = "Access-Control-Allow-Origin"


def assert_worker_error(response: httpx.Response, status: int) -> None:
    assert response.status_code == status
    assert response.headers[ERROR_HEADER] == "true"
    assert response.headers[CORS_ORIGIN_HEADER] == "*"
    assert list(response.json()) == ["error"]


def proxy(client: httpx.Client, target: str, method: str = "GET", **kwargs) -> httpx.Response:
    return client.request(method, "/", params={"url": target}, **kwargs)


# --- Authorization ---


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no key"),
        pytest.param({WORKER_KEY_HEADER: "wrong-key-of-other-len"}, id="wrong length"),
        pytest.param({WORKER_KEY_HEADER: TEST_KEY[:-1] + "!"}, id="same length"),
    ],
)
def test_request_without_valid_key_is_rejected(worker_url, upstream, headers):
    response = httpx.get(worker_url, params={"url": f"{upstream.url}/echo"}, headers=headers)
    assert_worker_error(response, 401)
    assert upstream.requests == []


def test_preflight_needs_no_key(worker_url):
    response = httpx.options(worker_url)
    assert response.status_code == 204
    assert response.headers[CORS_ORIGIN_HEADER] == "*"
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]
    assert response.headers["Access-Control-Allow-Headers"] == "*"


# --- Target URL ---


def test_target_from_query(client, upstream):
    response = proxy(client, f"{upstream.url}/echo")
    assert response.status_code == 200
    assert response.json()["path"] == "/echo"


def test_target_from_header(client, upstream):
    response = client.get("/", headers={"X-Target-URL": f"{upstream.url}/from-header"})
    assert response.json()["path"] == "/from-header"


def test_target_from_path(client, upstream):
    response = client.get(f"/{upstream.url}/from-path?a=1")
    assert response.json()["path"] == "/from-path?a=1"


def test_query_target_wins_over_header(client, upstream):
    response = client.get(
        "/",
        params={"url": f"{upstream.url}/from-query"},
        headers={"X-Target-URL": f"{upstream.url}/from-header"},
    )
    assert response.json()["path"] == "/from-query"


def test_missing_target(client):
    assert_worker_error(client.get("/"), 400)


@pytest.mark.parametrize("target", ["not a url", "ftp://example.com/", "file:///etc/passwd"])
def test_invalid_target(client, upstream, target):
    assert_worker_error(proxy(client, target), 400)
    assert upstream.requests == []


# --- Target query ---


def test_target_keeps_its_own_query(client, upstream):
    query = "a=1&s=two%20words&empty=&url=own&_t=own&_cb=own"
    response = proxy(client, f"{upstream.url}/echo?{query}")
    assert response.json()["path"] == f"/echo?{query}"


def test_extra_params_are_appended_except_routing_ones(client, upstream):
    response = client.get(
        "/", params={"url": f"{upstream.url}/echo?a=1", "x": "2", "_cb": "3", "_t": "4"}
    )
    assert response.json()["path"] == "/echo?a=1&x=2"


# --- Request headers ---


def test_ordinary_headers_are_forwarded(client, upstream):
    sent = {"User-Agent": "contract", "Authorization": "Bearer site", "X-Custom": "value"}
    headers = proxy(client, f"{upstream.url}/echo", headers=sent).json()["headers"]
    assert headers["user-agent"] == "contract"
    assert headers["authorization"] == "Bearer site"
    assert headers["x-custom"] == "value"


def test_service_and_client_identifying_headers_are_not_forwarded(client, upstream):
    sent = {
        "X-Target-URL": "http://unused.invalid/",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "client.example",
        "X-Real-IP": "9.9.9.9",
        "CF-Connecting-IP": "9.9.9.9",
    }
    headers = proxy(client, f"{upstream.url}/echo", headers=sent).json()["headers"]
    assert WORKER_KEY_HEADER.lower() not in headers
    assert TEST_KEY not in headers.values()
    assert "x-target-url" not in headers
    assert "x-forwarded-host" not in headers
    assert "x-real-ip" not in headers
    assert "9.9.9.9" not in headers.values()


def test_forwarded_for_replaces_client_value_with_random_ip(client, upstream):
    response = proxy(client, f"{upstream.url}/echo", headers={"X-Forwarded-For": "9.9.9.9"})
    forwarded_for = response.json()["headers"]["x-forwarded-for"]
    assert re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", forwarded_for)
    assert forwarded_for != "9.9.9.9"
    assert all(1 <= int(octet) <= 255 for octet in forwarded_for.split("."))


def test_forwarded_for_can_be_set_explicitly(client, upstream):
    sent = {"X-My-X-Forwarded-For": "5.6.7.8"}
    headers = proxy(client, f"{upstream.url}/echo", headers=sent).json()["headers"]
    assert headers["x-forwarded-for"] == "5.6.7.8"
    assert "x-my-x-forwarded-for" not in headers


# --- Methods and bodies ---


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_method_and_body_are_forwarded(client, upstream, method):
    echo = proxy(client, f"{upstream.url}/echo", method=method, content=b"payload").json()
    assert echo["method"] == method
    assert echo["body"] == "payload"


def test_head_has_no_body(client, upstream):
    response = proxy(client, f"{upstream.url}/echo", method="HEAD")
    assert response.status_code == 200
    assert response.content == b""
    assert upstream.requests[-1]["method"] == "HEAD"


# --- Response ---


@pytest.mark.parametrize("status", [201, 204, 304, 403, 404, 429, 500, 503])
def test_status_passes_through_as_a_site_response(client, upstream, status):
    response = proxy(client, f"{upstream.url}/status/{status}")
    assert response.status_code == status
    assert response.headers["X-Upstream"] == "yes"
    assert response.headers[CORS_ORIGIN_HEADER] == "*"
    assert ERROR_HEADER not in response.headers


def test_multiple_cookies_are_kept(client, upstream):
    response = proxy(client, f"{upstream.url}/cookies")
    assert response.headers.get_list("Set-Cookie") == ["a=1", "b=2"]


def test_compressed_body_arrives_decoded(client, upstream):
    # Without this header the runtime compresses the response again on the way to the client
    response = proxy(client, f"{upstream.url}/gzip", headers={"Accept-Encoding": "identity"})
    assert response.content == b"compressed text"
    assert "Content-Encoding" not in response.headers


def test_binary_body_is_intact(client, upstream):
    assert proxy(client, f"{upstream.url}/binary").content == BINARY_BODY


def test_redirect_is_followed_by_the_worker(client, upstream):
    response = proxy(client, f"{upstream.url}/redirect")
    assert response.status_code == 200
    assert response.json()["path"] == "/echo?from=redirect"


def test_unreachable_target(client):
    assert_worker_error(proxy(client, "http://127.0.0.1:1/"), 502)


def test_error_hides_internal_details(client):
    response = proxy(client, "http://127.0.0.1:1/")
    assert response.json() == {"error": "Proxy request failed"}


# --- Client library ---


def test_client_library_works_through_the_worker(worker_url, upstream):
    worker = WorkerRecord(name="w", url=worker_url, type="js", created_at=1.0, key=TEST_KEY)
    transport = ProxyflareTransport(ProxyflareWorkersManager([worker]))

    with httpx.Client(transport=transport, timeout=20) as client:
        response = client.post(f"{upstream.url}/echo?a=1&b=two%20words", content=b"payload")

    assert response.status_code == 200
    echo = response.json()
    assert echo["path"] == "/echo?a=1&b=two%20words"
    assert echo["body"] == "payload"
    assert WORKER_KEY_HEADER.lower() not in echo["headers"]


# --- pf md ---


def run_pf_md(worker_url, url, tmp_path, key=TEST_KEY):
    worker = WorkerRecord(name="w", url=worker_url, type="js", created_at=1.0, key=key)
    workers_file = tmp_path / "workers.json"
    WorkerResultFile(root=[worker]).save(workers_file)
    args = ["md", url, "--workers-file", str(workers_file), "--output", str(tmp_path / "out")]
    return CliRunner().invoke(app, args)


@pytest.mark.parametrize("route", ["/article", "/article-1251"])
def test_pf_md_saves_article(worker_url, upstream, tmp_path, route):
    url = f"{upstream.url}{route}?a=1"

    result = run_pf_md(worker_url, url, tmp_path)

    assert result.exit_code == 0, result.output
    saved = tmp_path / "out" / "заголовок-статьи.md"
    assert result.stdout.strip() == str(saved)
    text = saved.read_text(encoding="utf-8")
    assert f'source: "{url}"' in text
    assert "Съешь же ещё" in text
    assert upstream.requests[-1]["path"] == f"{route}?a=1"
    assert "Mozilla" in upstream.requests[-1]["headers"]["user-agent"]


def test_pf_md_reports_site_error_without_retrying(worker_url, upstream, tmp_path):
    result = run_pf_md(worker_url, f"{upstream.url}/status/404", tmp_path)

    assert result.exit_code == 1
    assert isinstance(result.exception, FetchError)
    assert "HTTP 404" in str(result.exception)
    assert len(upstream.requests) == 1


def test_pf_md_treats_rejected_key_as_worker_failure(worker_url, upstream, tmp_path):
    """A 401 from the worker must not be reported as if the site had refused."""
    result = run_pf_md(worker_url, f"{upstream.url}/article", tmp_path, key="wrong-key")

    assert result.exit_code == 1
    assert "all 1 attempts failed" in str(result.exception)
    assert upstream.requests == []
