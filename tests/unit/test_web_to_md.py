import json
import sys
from datetime import date

import httpx
import pytest

import web_to_md

WORKER_HEADERS = {"access-control-allow-origin": "*"}
HTML_TEMPLATE = (
    "<html><head>{meta}<title>Заголовок статьи</title></head><body><article>"
    "<h1>Заголовок статьи</h1><p>{text}</p><p>{text}</p></article></body></html>"
)
ARTICLE_TEXT = "Съешь же ещё этих мягких французских булок, да выпей чаю. " * 12


def worker_response(status_code=200, content=b"<html></html>", content_type="text/html"):
    headers = {**WORKER_HEADERS, "content-type": content_type}
    return httpx.Response(status_code, headers=headers, content=content)


@pytest.fixture
def proxy_config(tmp_path):
    records = [
        {
            "name": f"worker-{index}",
            "url": f"https://worker-{index}.example.workers.dev",
            "type": "rust",
            "created_at": 1.0,
            "key": "test-key",
        }
        for index in range(3)
    ]
    path = tmp_path / "workers.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.fixture
def scripted_requests(monkeypatch):
    """Подменяет сеть: каждый запрос получает следующий заранее заданный результат."""

    def install(*outcomes):
        calls = []
        remaining = list(outcomes)

        def fake_request_page(url, worker_url):
            calls.append(worker_url)
            outcome = remaining.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(web_to_md, "request_page", fake_request_page)
        return calls

    return install


class TestFetchHtml:
    def test_retries_on_other_worker_after_transport_error(self, proxy_config, scripted_requests):
        calls = scripted_requests(httpx.ConnectError("down"), worker_response(content=b"ok"))

        assert web_to_md.fetch_html("https://site.test", proxy_config) == b"ok"
        assert len(calls) == 2
        assert calls[0] != calls[1]

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_retries_when_worker_reports_failure(
        self, proxy_config, scripted_requests, status_code
    ):
        calls = scripted_requests(
            worker_response(status_code=status_code), worker_response(content=b"ok")
        )

        assert web_to_md.fetch_html("https://site.test", proxy_config) == b"ok"
        assert len(calls) == 2

    def test_retries_when_response_comes_from_deleted_worker(self, proxy_config, scripted_requests):
        calls = scripted_requests(httpx.Response(404), worker_response(content=b"ok"))

        assert web_to_md.fetch_html("https://site.test", proxy_config) == b"ok"
        assert len(calls) == 2

    @pytest.mark.parametrize("status_code", [403, 404])
    def test_does_not_retry_site_errors(self, proxy_config, scripted_requests, capsys, status_code):
        calls = scripted_requests(worker_response(status_code=status_code))

        assert web_to_md.fetch_html("https://site.test", proxy_config) is None
        assert len(calls) == 1
        assert f"HTTP {status_code}" in capsys.readouterr().err

    def test_gives_up_after_each_worker_failed(self, proxy_config, scripted_requests, capsys):
        calls = scripted_requests(*[httpx.ConnectError("down") for _ in range(3)])

        assert web_to_md.fetch_html("https://site.test", proxy_config) is None
        assert len({worker.url for worker in calls}) == 3
        assert "все попытки исчерпаны" in capsys.readouterr().err

    def test_does_not_expose_worker_url_in_errors(self, proxy_config, scripted_requests, capsys):
        scripted_requests(worker_response(status_code=403))

        web_to_md.fetch_html("https://site.test", proxy_config)

        captured = capsys.readouterr()
        assert "workers.dev" not in captured.out + captured.err

    def test_reports_missing_config(self, tmp_path, capsys):
        assert web_to_md.fetch_html("https://site.test", tmp_path / "missing.json") is None
        assert "Ошибка настройки воркеров" in capsys.readouterr().err


class TestEncoding:
    @pytest.mark.parametrize(
        ("content_type", "meta"),
        [
            ("text/html", '<meta charset="windows-1251">'),
            ("text/html", ""),
            ("text/html; charset=windows-1251", ""),
        ],
    )
    def test_windows_1251_page_keeps_cyrillic(
        self, proxy_config, scripted_requests, content_type, meta
    ):
        page = HTML_TEMPLATE.format(meta=meta, text=ARTICLE_TEXT).encode("cp1251")
        scripted_requests(worker_response(content=page, content_type=content_type))

        html = web_to_md.fetch_html("https://site.test", proxy_config)
        title, content = web_to_md.extract_content(html)

        assert title == "Заголовок статьи"
        assert "Съешь же ещё" in content


class TestSlugify:
    def test_keeps_cyrillic_and_replaces_separators(self):
        assert web_to_md.slugify("Привет, мир: тест_1") == "привет-мир-тест-1"

    def test_falls_back_when_title_has_no_usable_characters(self):
        assert web_to_md.slugify("!!! ???") == "article"

    def test_limits_length_in_bytes_without_breaking_characters(self):
        slug = web_to_md.slugify("ж" * 500)

        assert len(slug.encode()) <= web_to_md.MAX_SLUG_BYTES
        assert set(slug) == {"ж"}

    def test_truncated_slug_does_not_end_with_separator(self):
        assert not web_to_md.slugify("a" * 199 + " " + "b" * 50).endswith("-")


class TestFormatDocument:
    def test_adds_metadata_and_heading(self):
        document = web_to_md.format_document("Заголовок", "https://site.test/a", "Текст")

        assert document == (
            "---\n"
            'title: "Заголовок"\n'
            'source: "https://site.test/a"\n'
            f"saved: {date.today().isoformat()}\n"
            "---\n\n"
            "# Заголовок\n\n"
            "Текст\n"
        )

    def test_does_not_duplicate_heading_already_in_content(self):
        document = web_to_md.format_document(
            "Статья — Сайт", "https://site.test", "# Статья\n\nТекст"
        )

        assert 'title: "Статья — Сайт"\n' in document
        assert document.endswith("---\n\n# Статья\n\nТекст\n")

    def test_escapes_special_characters_in_title(self):
        document = web_to_md.format_document('Он сказал: "да"\nи ушёл', "https://site.test", "x")

        assert 'title: "Он сказал: \\"да\\" и ушёл"\n' in document
        assert '# Он сказал: "да" и ушёл\n' in document


class TestSaveMarkdown:
    def test_creates_missing_directory(self, tmp_path):
        output_dir = tmp_path / "a" / "b"

        path = web_to_md.save_markdown("Заголовок", "текст", output_dir)

        assert path == output_dir / "заголовок.md"
        assert path.read_text(encoding="utf-8") == "текст"

    def test_does_not_overwrite_existing_file(self, tmp_path):
        first = web_to_md.save_markdown("Заголовок", "первый", tmp_path)
        second = web_to_md.save_markdown("Заголовок", "второй", tmp_path)

        assert first != second
        assert first.read_text(encoding="utf-8") == "первый"

    def test_saves_very_long_title(self, tmp_path):
        path = web_to_md.save_markdown("ж" * 500, "текст", tmp_path)

        assert path is not None
        assert path.exists()

    def test_returns_none_when_directory_cannot_be_created(self, tmp_path, capsys):
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")

        assert web_to_md.save_markdown("Заголовок", "текст", blocker / "sub") is None
        assert "Ошибка при сохранении" in capsys.readouterr().err


class TestMain:
    def run_main(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["web_to_md.py", *args])
        return web_to_md.main()

    def test_returns_zero_and_writes_file(
        self, monkeypatch, tmp_path, proxy_config, scripted_requests
    ):
        page = HTML_TEMPLATE.format(meta="", text=ARTICLE_TEXT).encode()
        scripted_requests(worker_response(content=page))

        code = self.run_main(
            monkeypatch, "https://site.test/a", "-o", str(tmp_path / "out"), "-p", str(proxy_config)
        )

        assert code == 0
        saved = (tmp_path / "out" / "заголовок-статьи.md").read_text(encoding="utf-8")
        assert 'source: "https://site.test/a"' in saved
        assert "Съешь же ещё" in saved

    def test_returns_one_when_fetch_fails(
        self, monkeypatch, tmp_path, proxy_config, scripted_requests
    ):
        scripted_requests(worker_response(status_code=403))

        code = self.run_main(
            monkeypatch, "https://site.test", "-o", str(tmp_path), "-p", str(proxy_config)
        )

        assert code == 1

    def test_returns_one_when_no_content_found(
        self, monkeypatch, tmp_path, proxy_config, scripted_requests, capsys
    ):
        scripted_requests(worker_response(content=b"<html><body></body></html>"))

        code = self.run_main(
            monkeypatch, "https://site.test", "-o", str(tmp_path), "-p", str(proxy_config)
        )

        assert code == 1
        assert "Контент не найден" in capsys.readouterr().err

    def test_default_paths_do_not_depend_on_working_directory(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["web_to_md.py", "https://site.test"])

        args = web_to_md.parse_args()

        assert args.proxy_config == web_to_md.SCRIPT_DIR / "proxyflare-workers.json"
        assert args.output == web_to_md.SCRIPT_DIR / "articles"
