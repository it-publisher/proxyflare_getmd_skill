from datetime import date

import httpx
import pytest

from proxyflare import markdown
from proxyflare.exceptions import FetchError
from proxyflare.markdown import Article
from proxyflare.models.worker_result import WorkerRecord

HTML_TEMPLATE = (
    "<html><head>{meta}<title>Заголовок статьи</title></head><body><article>"
    "<h1>Заголовок статьи</h1><p>{text}</p><p>{text}</p></article></body></html>"
)
ARTICLE_TEXT = "Съешь же ещё этих мягких французских булок, да выпей чаю. " * 12


def site_response(status_code=200, content=b"<html></html>", content_type="text/html"):
    headers = {"access-control-allow-origin": "*", "content-type": content_type}
    return httpx.Response(status_code, headers=headers, content=content)


def worker_error_response(status_code):
    headers = {"access-control-allow-origin": "*", "x-proxyflare-error": "true"}
    return httpx.Response(status_code, headers=headers, json={"error": "failed"})


@pytest.fixture
def workers():
    return [
        WorkerRecord(
            name=f"worker-{index}",
            url=f"https://worker-{index}.example.workers.dev",
            type="rust",
            created_at=1.0,
            key="test-key",
        )
        for index in range(3)
    ]


@pytest.fixture
def scripted_requests(monkeypatch):
    """Replace the network: each request gets the next prepared outcome."""

    def install(*outcomes):
        calls = []
        remaining = list(outcomes)

        def fake_request_page(url, worker):
            calls.append(worker)
            outcome = remaining.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(markdown, "_request_page", fake_request_page)
        return calls

    return install


class TestFetchHtml:
    def test_retries_on_other_worker_after_transport_error(self, workers, scripted_requests):
        calls = scripted_requests(httpx.ConnectError("down"), site_response(content=b"ok"))

        assert markdown.fetch_html("https://site.test", workers) == b"ok"
        assert len(calls) == 2
        assert calls[0] != calls[1]

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_retries_when_server_side_status(self, workers, scripted_requests, status_code):
        calls = scripted_requests(
            site_response(status_code=status_code), site_response(content=b"ok")
        )

        assert markdown.fetch_html("https://site.test", workers) == b"ok"
        assert len(calls) == 2

    def test_retries_when_response_comes_from_deleted_worker(self, workers, scripted_requests):
        calls = scripted_requests(httpx.Response(404), site_response(content=b"ok"))

        assert markdown.fetch_html("https://site.test", workers) == b"ok"
        assert len(calls) == 2

    @pytest.mark.parametrize("status_code", [400, 401, 502])
    def test_retries_when_worker_itself_reports_error(
        self, workers, scripted_requests, status_code
    ):
        calls = scripted_requests(worker_error_response(status_code), site_response(content=b"ok"))

        assert markdown.fetch_html("https://site.test", workers) == b"ok"
        assert len(calls) == 2

    @pytest.mark.parametrize("status_code", [401, 403, 404])
    def test_does_not_retry_site_errors(self, workers, scripted_requests, status_code):
        calls = scripted_requests(site_response(status_code=status_code))

        with pytest.raises(FetchError, match=f"HTTP {status_code}"):
            markdown.fetch_html("https://site.test", workers)
        assert len(calls) == 1

    def test_gives_up_after_each_worker_failed(self, workers, scripted_requests):
        calls = scripted_requests(*[httpx.ConnectError("down") for _ in range(3)])

        with pytest.raises(FetchError, match="all 3 attempts failed"):
            markdown.fetch_html("https://site.test", workers)
        assert len({worker.url for worker in calls}) == 3

    def test_reports_each_failed_attempt_without_worker_url(self, workers, scripted_requests):
        scripted_requests(
            httpx.ReadTimeout(""), site_response(status_code=500), httpx.Response(404)
        )
        messages = []

        with pytest.raises(FetchError):
            markdown.fetch_html("https://site.test", workers, on_attempt_failed=messages.append)

        assert messages == [
            "Attempt 1/3: ReadTimeout",
            "Attempt 2/3: HTTP 500",
            "Attempt 3/3: HTTP 404",
        ]


class TestEncoding:
    @pytest.mark.parametrize(
        ("content_type", "meta"),
        [
            ("text/html", '<meta charset="windows-1251">'),
            ("text/html", ""),
            ("text/html; charset=windows-1251", ""),
        ],
    )
    def test_windows_1251_page_keeps_cyrillic(self, workers, scripted_requests, content_type, meta):
        page = HTML_TEMPLATE.format(meta=meta, text=ARTICLE_TEXT).encode("cp1251")
        scripted_requests(site_response(content=page, content_type=content_type))

        article = markdown.extract_article(markdown.fetch_html("https://site.test", workers))

        assert article.title == "Заголовок статьи"
        assert "Съешь же ещё" in article.content


def large_page():
    paragraphs = "".join(
        f"<p>Paragraph {i} with enough words to count as text.</p>" for i in range(600)
    )
    return f"<html><head><title>T</title></head><body>{paragraphs}</body></html>"


class TestExtractArticle:
    def test_keeps_formatting_normally(self):
        html = HTML_TEMPLATE.format(meta="", text=ARTICLE_TEXT)

        article = markdown.extract_article(html)

        assert article.has_formatting is True
        assert article.content.startswith("# Заголовок статьи")

    def test_returns_none_without_content(self):
        assert markdown.extract_article(b"<html><body></body></html>") is None

    def test_falls_back_to_whole_text_when_most_of_the_page_is_lost(self, monkeypatch):
        """extract() is replaced because the mistake showed up only on a real RFC page."""
        monkeypatch.setattr(markdown.trafilatura, "extract", lambda *_, **__: "one block")

        article = markdown.extract_article(large_page())

        assert article.has_formatting is False
        assert "Paragraph 599" in article.content

    def test_short_page_is_not_checked_for_lost_text(self, monkeypatch):
        html = "<html><head><title>T</title></head><body><p>Small page text.</p></body></html>"
        monkeypatch.setattr(markdown.trafilatura, "extract", lambda *_, **__: "x")

        assert markdown.extract_article(html).has_formatting is True

    @pytest.mark.parametrize(
        ("content_length", "is_lost"), [(999, True), (1000, False), (5000, False)]
    )
    def test_lost_text_threshold(self, content_length, is_lost):
        assert markdown._lost_most_of_the_page("x" * content_length, "y" * 10_000) is is_lost


class TestSlugify:
    def test_keeps_cyrillic_and_replaces_separators(self):
        assert markdown.slugify("Привет, мир: тест_1") == "привет-мир-тест-1"

    def test_falls_back_when_title_has_no_usable_characters(self):
        assert markdown.slugify("!!! ???") == "article"

    def test_limits_length_in_bytes_without_breaking_characters(self):
        slug = markdown.slugify("ж" * 500)

        assert len(slug.encode()) <= markdown.MAX_SLUG_BYTES
        assert set(slug) == {"ж"}

    def test_truncated_slug_does_not_end_with_separator(self):
        assert not markdown.slugify("a" * 199 + " " + "b" * 50).endswith("-")

    def test_path_separators_are_removed(self):
        assert markdown.slugify("../../etc/passwd") == "etcpasswd"


class TestFormatDocument:
    def test_adds_metadata_and_heading(self):
        document = markdown.format_document(Article("Заголовок", "Текст"), "https://site.test/a")

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
        document = markdown.format_document(
            Article("Статья — Сайт", "# Статья\n\nТекст"), "https://site.test"
        )

        assert 'title: "Статья — Сайт"\n' in document
        assert document.endswith("---\n\n# Статья\n\nТекст\n")

    def test_escapes_special_characters_in_title(self):
        document = markdown.format_document(
            Article('Он сказал: "да"\nи ушёл', "x"), "https://site.test"
        )

        assert 'title: "Он сказал: \\"да\\" и ушёл"\n' in document
        assert '# Он сказал: "да" и ушёл\n' in document


class TestSaveDocument:
    def test_creates_missing_directory(self, tmp_path):
        output_dir = tmp_path / "a" / "b"

        path = markdown.save_document("Заголовок", "текст", output_dir)

        assert path == output_dir / "заголовок.md"
        assert path.read_text(encoding="utf-8") == "текст"

    def test_does_not_overwrite_existing_files(self, tmp_path):
        paths = [markdown.save_document("Заголовок", f"версия {n}", tmp_path) for n in range(3)]

        assert [path.name for path in paths] == ["заголовок.md", "заголовок-2.md", "заголовок-3.md"]
        assert paths[0].read_text(encoding="utf-8") == "версия 0"

    def test_saves_very_long_title(self, tmp_path):
        assert markdown.save_document("ж" * 500, "текст", tmp_path).exists()

    def test_raises_when_directory_cannot_be_created(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")

        with pytest.raises(OSError):
            markdown.save_document("Заголовок", "текст", blocker / "sub")
