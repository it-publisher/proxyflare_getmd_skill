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

export async function fetchHtml(url: string): Promise<string> {
	const response = await fetch(url, {
		headers: {
			"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
			"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
		},
	});

	if (!response.ok) {
		throw new Error(`Fetch error: ${response.status}`);
	}

	return response.text();
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
