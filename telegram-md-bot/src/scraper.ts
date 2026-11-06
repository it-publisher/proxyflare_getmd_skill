import { Readability } from "@mozilla/readability";
import { parseHTML } from "linkedom";
import { NodeHtmlMarkdown } from "node-html-markdown";

const URL_PATTERN = /https?:\/\/[^\s<>]+/i;
const TRAILING_PUNCTUATION = /[.,;:!?'"»”’…]+$/;
const OPENING_BRACKETS: Record<string, string> = { ")": "(", "]": "[", "}": "{" };

const MAX_SLUG_LENGTH = 80;
const FALLBACK_SLUG = "article";

const RETRY_BASE_DELAY_MS = 1500;
const MAX_RETRY_DELAY_MS = 5000;
const FETCH_TIMEOUT_MS = 10_000;
const JINA_TIMEOUT_MS = 20_000;

const DEFAULT_CHARSET = "utf-8";
const META_CHARSET_SCAN_BYTES = 2048;

function hasUnmatchedClosingBracket(url: string): boolean {
	const closing = url.at(-1) ?? "";
	const opening = OPENING_BRACKETS[closing];
	if (!opening) return false;
	return url.split(closing).length > url.split(opening).length;
}

function trimUrlEnd(url: string): string {
	let trimmed = url.replace(TRAILING_PUNCTUATION, "");
	// Brackets stay when balanced: they are part of URLs like /wiki/Foo_(bar)
	while (hasUnmatchedClosingBracket(trimmed)) {
		trimmed = trimmed.slice(0, -1).replace(TRAILING_PUNCTUATION, "");
	}
	return trimmed;
}

export function extractUrl(text: string): string | null {
	const match = text.match(URL_PATTERN);
	if (!match) return null;

	const url = trimUrlEnd(match[0]);
	try {
		new URL(url);
		return url;
	} catch {
		return null;
	}
}

export function slugify(text: string): string {
	const slug = text
		.toLowerCase()
		.replace(/[^\p{L}\p{M}\p{N}\s_-]/gu, "")
		.replace(/[\s_-]+/g, "-")
		.replace(/^-+|-+$/g, "");
	// Array.from keeps surrogate pairs whole, which String.slice could cut in half
	const shortened = Array.from(slug).slice(0, MAX_SLUG_LENGTH).join("").replace(/-+$/, "");
	return shortened || FALLBACK_SLUG;
}

const USER_AGENTS = [
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Retry-After holds either seconds or an HTTP date. The wait is capped so a site can't stall the webhook. */
export function getRetryDelayMs(
	retryAfter: string | null,
	attempt: number,
	now = Date.now()
): number {
	const backoffMs = 2 ** attempt * RETRY_BASE_DELAY_MS;
	if (!retryAfter) return Math.min(backoffMs, MAX_RETRY_DELAY_MS);

	const seconds = Number(retryAfter);
	const requestedMs = Number.isNaN(seconds) ? Date.parse(retryAfter) - now : seconds * 1000;
	const delayMs = Number.isFinite(requestedMs) && requestedMs >= 0 ? requestedMs : backoffMs;
	return Math.min(delayMs, MAX_RETRY_DELAY_MS);
}

function detectCharset(bytes: Uint8Array, contentType: string | null): string {
	const headerCharset = contentType?.match(/charset=["']?([\w-]+)/i)?.[1];
	if (headerCharset) return headerCharset;

	const head = new TextDecoder().decode(bytes.subarray(0, META_CHARSET_SCAN_BYTES));
	return head.match(/<meta[^>]+charset=["']?([\w-]+)/i)?.[1] ?? DEFAULT_CHARSET;
}

export function decodeHtml(bytes: Uint8Array, contentType: string | null): string {
	try {
		return new TextDecoder(detectCharset(bytes, contentType)).decode(bytes);
	} catch (err) {
		if (!(err instanceof RangeError)) throw err;
		// The page named a charset the runtime doesn't know
		return new TextDecoder(DEFAULT_CHARSET).decode(bytes);
	}
}

export async function fetchHtml(url: string, maxRetries = 3): Promise<string> {
	let lastStatus = 0;

	for (let attempt = 0; attempt < maxRetries; attempt++) {
		const response = await fetch(url, {
			headers: {
				"User-Agent": USER_AGENTS[attempt % USER_AGENTS.length],
				"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
				"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
				"Cache-Control": "no-cache",
			},
			signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
		});

		if (response.ok) {
			const bytes = new Uint8Array(await response.arrayBuffer());
			return decodeHtml(bytes, response.headers.get("Content-Type"));
		}

		lastStatus = response.status;

		if (response.status === 429 && attempt < maxRetries - 1) {
			await sleep(getRetryDelayMs(response.headers.get("Retry-After"), attempt));
			continue;
		}

		break;
	}

	throw new Error(`Fetch error: ${lastStatus}`);
}

async function fetchJina(url: string, apiKey?: string): Promise<string> {
	const headers: Record<string, string> = {
		"Accept": "text/markdown,text/plain,*/*",
		"User-Agent": USER_AGENTS[0],
	};
	if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

	const response = await fetch(`https://r.jina.ai/${url}`, {
		headers,
		signal: AbortSignal.timeout(JINA_TIMEOUT_MS),
	});
	if (!response.ok) throw new Error(`Jina fetch error: ${response.status}`);
	return response.text();
}

export interface FetchResult {
	content: string;
	isMarkdown: boolean;
}

export async function fetchContent(url: string, jinaApiKey?: string): Promise<FetchResult> {
	try {
		const html = await fetchHtml(url);
		return { content: html, isMarkdown: false };
	} catch (err) {
		const msg = err instanceof Error ? err.message : String(err);
		if (msg.includes("429") || msg.includes("403")) {
			const markdown = await fetchJina(url, jinaApiKey);
			return { content: markdown, isMarkdown: true };
		}
		throw err;
	}
}

export interface ParsedArticle {
	title: string;
	markdown: string;
}

export function parseArticle(html: string, url: string): ParsedArticle {
	const { document } = parseHTML(html);

	// Readability 0.6.x needs these DOM APIs — patch missing linkedom methods
	const makePatchedDoc = (title = "") => {
		const doc = parseHTML(
			`<!DOCTYPE html><html><head><title>${title}</title></head><body></body></html>`
		).document;
		let buf = "";
		Object.assign(doc, {
			open() { buf = ""; },
			write(chunk: string) { buf += chunk; },
			close() {
				if (buf) {
					const { document: fresh } = parseHTML(buf);
					doc.body.innerHTML = fresh.body?.innerHTML ?? "";
					doc.head.innerHTML = fresh.head?.innerHTML ?? "";
				}
			},
		});
		return doc;
	};

	Object.assign(document, {
		implementation: { createHTMLDocument: makePatchedDoc },
	});

	const reader = new Readability(
		document as unknown as ConstructorParameters<typeof Readability>[0]
	);
	const article = reader.parse();

	if (!article) {
		throw new Error("Readability не смог извлечь контент");
	}

	const markdown = NodeHtmlMarkdown.translate(article.content ?? "");

	return {
		title: article.title || "article",
		markdown,
	};
}
