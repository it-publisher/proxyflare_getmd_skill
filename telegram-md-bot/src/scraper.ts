import { Readability } from "@mozilla/readability";
import { parseHTML } from "linkedom";
import { NodeHtmlMarkdown } from "node-html-markdown";

export function extractUrl(text: string): string | null {
	const match = text.match(/https?:\/\/[^\s]+/);
	return match ? match[0] : null;
}

export function slugify(text: string): string {
	return text
		.toLowerCase()
		.replace(/[^\w\s-]/g, "")
		.replace(/[\s_]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 80);
}

const USER_AGENTS = [
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

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
		});

		if (response.ok) return response.text();

		lastStatus = response.status;

		if (response.status === 429 && attempt < maxRetries - 1) {
			const retryAfter = response.headers.get("Retry-After");
			const delay = retryAfter ? parseInt(retryAfter) * 1000 : 2 ** attempt * 1500;
			await sleep(delay);
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

	const response = await fetch(`https://r.jina.ai/${url}`, { headers });
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

	const reader = new Readability(document as unknown as Document);
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
