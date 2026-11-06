import json
from unittest.mock import patch

import httpx
import pytest
import respx
from typer.testing import CliRunner

from proxyflare.cli.app import app
from proxyflare.cli.exceptions import ConfigError, WorkerError
from proxyflare.exceptions import FetchError

runner = CliRunner()

WORKER_URL = "https://worker.test"
TARGET = "https://site.test/a?x=1"
ARTICLE_TEXT = "Съешь же ещё этих мягких французских булок, да выпей чаю. " * 12
PAGE = (
    "<html><head><title>Заголовок статьи</title></head><body><article><h1>Заголовок статьи</h1>"
    f"<p>{ARTICLE_TEXT}</p><p>{ARTICLE_TEXT}</p></article></body></html>"
)
SITE_HEADERS = {"access-control-allow-origin": "*", "content-type": "text/html; charset=utf-8"}


@pytest.fixture
def workers_file(tmp_path):
    record = {"name": "w", "url": WORKER_URL, "type": "js", "created_at": 1.0, "key": "secret-key"}
    path = tmp_path / "workers.json"
    path.write_text(json.dumps([record]))
    return path


def run_md(workers_file, output, url=TARGET):
    args = ["md", url, "--workers-file", str(workers_file), "--output", str(output)]
    return runner.invoke(app, args)


@respx.mock
def test_saves_article_and_prints_only_its_path(workers_file, tmp_path):
    route = respx.get(WORKER_URL).mock(
        return_value=httpx.Response(200, headers=SITE_HEADERS, text=PAGE)
    )

    result = run_md(workers_file, tmp_path / "out")

    assert result.exit_code == 0
    saved = tmp_path / "out" / "заголовок-статьи.md"
    assert result.stdout.strip() == str(saved)
    text = saved.read_text(encoding="utf-8")
    assert f'source: "{TARGET}"' in text
    assert "Съешь же ещё" in text
    assert route.calls.last.request.headers["X-Proxyflare-Key"] == "secret-key"
    assert route.calls.last.request.url.params["url"] == TARGET


@respx.mock
def test_uses_workers_file_from_config_dir_by_default(
    workers_file, isolated_config_dir, tmp_path, monkeypatch
):
    isolated_config_dir.mkdir()
    (isolated_config_dir / "workers.json").write_text(workers_file.read_text())
    respx.get(WORKER_URL).mock(return_value=httpx.Response(200, headers=SITE_HEADERS, text=PAGE))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["md", TARGET])

    assert result.exit_code == 0
    assert (tmp_path / "articles" / "заголовок-статьи.md").exists()


@respx.mock
def test_site_error_fails_without_saving(workers_file, tmp_path):
    respx.get(WORKER_URL).mock(return_value=httpx.Response(403, headers=SITE_HEADERS))

    result = run_md(workers_file, tmp_path / "out")

    assert result.exit_code == 1
    assert isinstance(result.exception, FetchError)
    assert not (tmp_path / "out").exists()


@respx.mock
def test_page_without_article_fails(workers_file, tmp_path):
    respx.get(WORKER_URL).mock(
        return_value=httpx.Response(200, headers=SITE_HEADERS, text="<html><body></body></html>")
    )

    result = run_md(workers_file, tmp_path / "out")

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert "No article found" in str(result.exception)


@respx.mock
def test_unwritable_output_fails_with_clear_error(workers_file, tmp_path):
    respx.get(WORKER_URL).mock(return_value=httpx.Response(200, headers=SITE_HEADERS, text=PAGE))
    blocker = tmp_path / "file"
    blocker.write_text("x")

    result = run_md(workers_file, blocker / "sub")

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert "Could not save" in str(result.exception)


@respx.mock
def test_warns_when_formatting_was_lost(workers_file, tmp_path):
    respx.get(WORKER_URL).mock(return_value=httpx.Response(200, headers=SITE_HEADERS, text=PAGE))

    with (
        patch("proxyflare.markdown._lost_most_of_the_page", return_value=True),
        patch("proxyflare.cli.commands.md.print_warning") as warn,
    ):
        result = run_md(workers_file, tmp_path / "out")

    assert result.exit_code == 0
    assert "without formatting" in warn.call_args.args[0]


def test_missing_workers_file_gives_a_hint(tmp_path):
    result = run_md(tmp_path / "missing.json", tmp_path)

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert "pf create" in str(result.exception)


def test_invalid_workers_file_does_not_reveal_keys(tmp_path):
    path = tmp_path / "workers.json"
    path.write_text('[{"name": "w", "key": "secret-key"}]')

    result = run_md(path, tmp_path)

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert "secret-key" not in str(result.exception)


@pytest.mark.parametrize("url", ["example.com/a", "ftp://example.com/a", "https://"])
def test_invalid_url_is_rejected_before_any_request(workers_file, tmp_path, url):
    result = run_md(workers_file, tmp_path, url=url)
    assert result.exit_code == 2
