import { describe, it, expect, vi, beforeEach } from "vitest";
import {
	decodeHtml,
	extractUrl,
	fetchContent,
	getRetryDelayMs,
	parseArticle,
	slugify,
} from "../src/scraper";

const WINDOWS_1251_PRIVET = new Uint8Array([0xcf, 0xf0, 0xe8, 0xe2, 0xe5, 0xf2]);

describe("extractUrl", () => {
	it.each([
		["смотри https://habr.com/ru/articles/1/ тут", "https://habr.com/ru/articles/1/"],
		["https://example.com/a.", "https://example.com/a"],
		["https://example.com/a?!", "https://example.com/a"],
		["(см. https://example.com/a).", "https://example.com/a"],
		["«https://example.com/a»", "https://example.com/a"],
		["<https://example.com/a>", "https://example.com/a"],
		["https://ru.wikipedia.org/wiki/Foo_(bar)", "https://ru.wikipedia.org/wiki/Foo_(bar)"],
		["(https://ru.wikipedia.org/wiki/Foo_(bar))", "https://ru.wikipedia.org/wiki/Foo_(bar)"],
		["https://example.com/?a=1&b=2", "https://example.com/?a=1&b=2"],
		["HTTPS://EXAMPLE.COM/a", "HTTPS://EXAMPLE.COM/a"],
	])("%s → %s", (text, expected) => {
		expect(extractUrl(text)).toBe(expected);
	});

	it.each(["просто текст", "ftp://example.com", "https://..."])("%s → null", (text) => {
		expect(extractUrl(text)).toBeNull();
	});
});

describe("slugify", () => {
	it.each([
		["Как работает Cloudflare", "как-работает-cloudflare"],
		["Привет, мир!", "привет-мир"],
		["Hello_World - test", "hello-world-test"],
		["../../etc/passwd", "etcpasswd"],
		["日本語のタイトル", "日本語のタイトル"],
		["!!!", "article"],
		["", "article"],
	])("%s → %s", (text, expected) => {
		expect(slugify(text)).toBe(expected);
	});

	it("keeps combining marks", () => {
		expect(slugify("й")).toBe("й");
	});

	it("limits length without a trailing hyphen", () => {
		const slug = slugify(`${"а".repeat(79)} ${"б".repeat(10)}`);
		expect(slug).toBe("а".repeat(79));
	});

	it("doesn't split surrogate pairs", () => {
		expect(slugify("𝒜".repeat(100))).toBe("𝒜".repeat(80));
	});
});

describe("getRetryDelayMs", () => {
	const NOW = Date.parse("2026-01-01T00:00:00Z");

	it.each([
		["seconds", "2", 2000],
		["zero", "0", 0],
		["capped seconds", "3600", 5000],
		["HTTP date", "Thu, 01 Jan 2026 00:00:03 GMT", 3000],
		["capped HTTP date", "Fri, 02 Jan 2026 00:00:00 GMT", 5000],
		["past HTTP date → backoff", "Wed, 31 Dec 2025 00:00:00 GMT", 1500],
		["garbage → backoff", "soon", 1500],
		["negative → backoff", "-5", 1500],
		["absent → backoff", null, 1500],
	])("%s", (_name, header, expected) => {
		expect(getRetryDelayMs(header, 0, NOW)).toBe(expected);
	});

	it("caps exponential backoff", () => {
		expect(getRetryDelayMs(null, 10, NOW)).toBe(5000);
	});
});

describe("decodeHtml", () => {
	it("uses the charset from the Content-Type header", () => {
		expect(decodeHtml(WINDOWS_1251_PRIVET, "text/html; charset=windows-1251")).toBe("Привет");
	});

	it("uses the charset from a meta tag when the header has none", () => {
		const meta = new TextEncoder().encode('<meta charset="windows-1251">');
		const html = new Uint8Array([...meta, ...WINDOWS_1251_PRIVET]);
		expect(decodeHtml(html, "text/html")).toContain("Привет");
	});

	it("defaults to UTF-8", () => {
		expect(decodeHtml(new TextEncoder().encode("Привет"), null)).toBe("Привет");
	});

	it("falls back to UTF-8 for an unknown charset", () => {
		const bytes = new TextEncoder().encode("Привет");
		expect(decodeHtml(bytes, "text/html; charset=no-such-charset")).toBe("Привет");
	});
});

describe("fetchContent", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	it("returns HTML from a successful response", async () => {
		vi.mocked(fetch).mockResolvedValueOnce(new Response("<html></html>"));
		const result = await fetchContent("https://example.com");
		expect(result).toEqual({ content: "<html></html>", isMarkdown: false });
	});

	it("retries after 429", async () => {
		vi.mocked(fetch)
			.mockResolvedValueOnce(new Response("", { status: 429, headers: { "Retry-After": "0" } }))
			.mockResolvedValueOnce(new Response("<html></html>"));
		const result = await fetchContent("https://example.com");
		expect(result.content).toBe("<html></html>");
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it("falls back to Jina on 403 and sends the API key", async () => {
		vi.mocked(fetch)
			.mockResolvedValueOnce(new Response("", { status: 403 }))
			.mockResolvedValueOnce(new Response("# Title"));
		const result = await fetchContent("https://example.com/a", "jina-key");
		expect(result).toEqual({ content: "# Title", isMarkdown: true });

		const [jinaUrl, jinaInit] = vi.mocked(fetch).mock.calls[1];
		expect(jinaUrl).toBe("https://r.jina.ai/https://example.com/a");
		expect((jinaInit?.headers as Record<string, string>).Authorization).toBe("Bearer jina-key");
	});

	it("falls back to Jina when 429 persists", async () => {
		vi.mocked(fetch).mockImplementation(async (input) =>
			String(input).startsWith("https://r.jina.ai/")
				? new Response("# Title")
				: new Response("", { status: 429, headers: { "Retry-After": "0" } })
		);
		const result = await fetchContent("https://example.com");
		expect(result.isMarkdown).toBe(true);
		expect(fetch).toHaveBeenCalledTimes(4);
	});

	it("doesn't use Jina on 404", async () => {
		vi.mocked(fetch).mockResolvedValueOnce(new Response("", { status: 404 }));
		await expect(fetchContent("https://example.com")).rejects.toThrow("Fetch error: 404");
		expect(fetch).toHaveBeenCalledOnce();
	});

	it("reports a failed Jina fallback", async () => {
		vi.mocked(fetch)
			.mockResolvedValueOnce(new Response("", { status: 403 }))
			.mockResolvedValueOnce(new Response("", { status: 500 }));
		await expect(fetchContent("https://example.com")).rejects.toThrow("Jina fetch error: 500");
	});
});

describe("parseArticle", () => {
	const paragraph = "Это достаточно длинный абзац статьи, чтобы Readability принял его за контент. ";

	it("extracts the title and converts the body to Markdown", () => {
		const html = `<!DOCTYPE html><html><head><title>Заголовок статьи</title></head><body>
			<nav><a href="/">Меню сайта</a></nav>
			<article><h1>Заголовок статьи</h1>
				<p>${paragraph.repeat(10)}<strong>важное слово</strong></p>
				<p>${paragraph.repeat(10)}</p>
			</article></body></html>`;

		const { title, markdown } = parseArticle(html, "https://example.com/a");

		expect(title).toBe("Заголовок статьи");
		expect(markdown).toContain("**важное слово**");
		expect(markdown).not.toContain("Меню сайта");
	});

	it("throws when there is nothing to extract", () => {
		const html = "<html><body></body></html>";
		expect(() => parseArticle(html, "https://example.com")).toThrow(
			"Readability не смог извлечь контент"
		);
	});
});
