import {
	env,
	createExecutionContext,
	waitOnExecutionContext,
} from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import worker from "../src/index";

vi.mock("../src/scraper", () => ({
	extractUrl: vi.fn((text: string) => {
		const match = text.match(/https?:\/\/[^\s]+/);
		return match ? match[0] : null;
	}),
	fetchHtml: vi.fn().mockResolvedValue("<html><body>content</body></html>"),
	parseArticle: vi.fn().mockReturnValue({ title: "Test Article", markdown: "# Test" }),
	slugify: vi.fn((text: string) => text.toLowerCase().replace(/\s+/g, "-")),
}));

const mockEnv = {
	...env,
	TELEGRAM_BOT_TOKEN: "test-token",
	ALLOWED_CHAT_ID: "42",
};

function makeRequest(body: unknown) {
	return new Request("https://telegram-md-bot.workers.dev/", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
}

beforeEach(() => {
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("ok")));
});

describe("telegram-md-bot", () => {
	it("GET → 200 OK", async () => {
		const req = new Request("https://example.com");
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(200);
	});

	it("POST invalid JSON → 400", async () => {
		const req = new Request("https://example.com", {
			method: "POST",
			body: "not json",
		});
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(400);
	});

	it("update without message → 200", async () => {
		const req = makeRequest({ update_id: 1 });
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(200);
	});

	it("unauthorized chat → 200, no action", async () => {
		const req = makeRequest({
			update_id: 1,
			message: { chat: { id: 999 }, text: "https://example.com" },
		});
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(200);
		expect(vi.mocked(fetch)).not.toHaveBeenCalled();
	});

	it("message without URL → sends help text", async () => {
		const req = makeRequest({
			update_id: 1,
			message: { chat: { id: 42 }, text: "hello" },
		});
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(200);
		expect(vi.mocked(fetch)).toHaveBeenCalledWith(
			expect.stringContaining("sendMessage"),
			expect.anything()
		);
	});

	it("valid URL → fetches and sends document", async () => {
		const req = makeRequest({
			update_id: 1,
			message: { chat: { id: 42 }, text: "https://habr.com/ru/articles/123/" },
		});
		const ctx = createExecutionContext();
		const res = await worker.fetch(req, mockEnv, ctx);
		await waitOnExecutionContext(ctx);
		expect(res.status).toBe(200);
		expect(vi.mocked(fetch)).toHaveBeenCalledWith(
			expect.stringContaining("sendDocument"),
			expect.anything()
		);
	});
});
