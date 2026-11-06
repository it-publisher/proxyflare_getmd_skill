import { env } from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import worker from "../src/index";
import { fetchContent } from "../src/scraper";

vi.mock("../src/scraper", () => ({
	extractUrl: vi.fn((text: string) => {
		const match = text.match(/https?:\/\/[^\s]+/);
		return match ? match[0] : null;
	}),
	fetchContent: vi.fn(),
	parseArticle: vi.fn().mockReturnValue({ title: "Test Article", markdown: "# Test" }),
	slugify: vi.fn((text: string) => text.toLowerCase().replace(/\s+/g, "-")),
}));

const WEBHOOK_SECRET = "test-webhook-secret";
const ADMIN_ID = 42;

const mockEnv = {
	...env,
	TELEGRAM_BOT_TOKEN: "test-token",
	ALLOWED_CHAT_ID: String(ADMIN_ID),
	WEBHOOK_SECRET,
};

function makeRequest(body: unknown, secret: string | null = WEBHOOK_SECRET) {
	const headers = new Headers({ "Content-Type": "application/json" });
	if (secret !== null) headers.set("X-Telegram-Bot-Api-Secret-Token", secret);
	return new Request("https://telegram-md-bot.workers.dev/", {
		method: "POST",
		headers,
		body: JSON.stringify(body),
	});
}

function makeMessage(chatId: number, text?: string) {
	return { update_id: 1, message: { chat: { id: chatId }, text } };
}

function callWorker(request: Request, workerEnv = mockEnv) {
	return worker.fetch(request, workerEnv);
}

function sentTexts(): string[] {
	return vi
		.mocked(fetch)
		.mock.calls.filter(([url]) => String(url).includes("sendMessage"))
		.map(([, init]) => JSON.parse(String(init?.body)).text);
}

beforeEach(async () => {
	vi.stubGlobal("fetch", vi.fn(async () => new Response("ok")));
	vi.mocked(fetchContent).mockReset();
	vi.mocked(fetchContent).mockResolvedValue({
		content: "<html><body>content</body></html>",
		isMarkdown: false,
	});
	const { keys } = await env.ALLOWED_USERS.list();
	await Promise.all(keys.map((key) => env.ALLOWED_USERS.delete(key.name)));
});

describe("webhook authentication", () => {
	it("GET → 200 OK without a secret", async () => {
		const res = await callWorker(new Request("https://example.com"));
		expect(res.status).toBe(200);
	});

	it.each([
		["missing", null],
		["wrong", "wrong-webhook-secret"],
		["different length", "short"],
	])("%s secret → 401, no action", async (_name, secret) => {
		const res = await callWorker(makeRequest(makeMessage(ADMIN_ID, "/add 777"), secret));
		expect(res.status).toBe(401);
		expect(await env.ALLOWED_USERS.get("777")).toBeNull();
		expect(vi.mocked(fetch)).not.toHaveBeenCalled();
	});

	it("rejects everything when WEBHOOK_SECRET is not configured", async () => {
		const res = await callWorker(makeRequest(makeMessage(ADMIN_ID, "/list"), ""), {
			...mockEnv,
			WEBHOOK_SECRET: "",
		});
		expect(res.status).toBe(401);
	});
});

describe("update handling", () => {
	it("POST invalid JSON → 400", async () => {
		const req = new Request("https://example.com", {
			method: "POST",
			headers: { "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET },
			body: "not json",
		});
		const res = await callWorker(req);
		expect(res.status).toBe(400);
	});

	it("update without message → 200", async () => {
		const res = await callWorker(makeRequest({ update_id: 1 }));
		expect(res.status).toBe(200);
	});

	it("unauthorized chat → 200, no action", async () => {
		const res = await callWorker(makeRequest(makeMessage(999, "https://example.com")));
		expect(res.status).toBe(200);
		expect(vi.mocked(fetch)).not.toHaveBeenCalled();
	});

	it("user from KV is allowed", async () => {
		await env.ALLOWED_USERS.put("555", "1");
		await callWorker(makeRequest(makeMessage(555, "hello")));
		expect(sentTexts()).toEqual(["Не нашёл URL в сообщении."]);
	});

	it("message without text → asks for a link", async () => {
		await callWorker(makeRequest(makeMessage(ADMIN_ID)));
		expect(sentTexts()).toEqual(["Отправь ссылку на статью."]);
	});

	it("valid URL → fetches and sends document", async () => {
		const res = await callWorker(
			makeRequest(makeMessage(ADMIN_ID, "https://habr.com/ru/articles/123/"))
		);
		expect(res.status).toBe(200);
		expect(vi.mocked(fetch)).toHaveBeenCalledWith(
			expect.stringContaining("sendDocument"),
			expect.anything()
		);
	});

	it("scraping failure → reports the error to the user", async () => {
		vi.mocked(fetchContent).mockRejectedValue(new Error("Fetch error: 404"));
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "https://example.com")));
		expect(sentTexts().at(-1)).toBe("❌ Ошибка: Fetch error: 404");
	});

	it("Telegram rejects the document → reports the reason without the token", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(async (url: string) =>
				url.includes("sendDocument")
					? Response.json({ description: "Bad Request: file is empty" }, { status: 400 })
					: new Response("ok")
			)
		);
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "https://example.com")));
		const lastText = sentTexts().at(-1);
		expect(lastText).toBe(
			"❌ Ошибка: Telegram sendDocument: HTTP 400, Bad Request: file is empty"
		);
		expect(lastText).not.toContain("test-token");
	});

	it("Telegram is down → logs the failure and still returns 200", async () => {
		const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
		vi.stubGlobal("fetch", vi.fn(async () => new Response("down", { status: 500 })));
		const res = await callWorker(makeRequest(makeMessage(ADMIN_ID, "https://example.com")));
		expect(res.status).toBe(200);
		expect(consoleError).toHaveBeenCalledOnce();
		consoleError.mockRestore();
	});
});

describe("admin commands", () => {
	it("/add stores the user", async () => {
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "/add 777")));
		expect(await env.ALLOWED_USERS.get("777")).toBe("1");
		expect(sentTexts()).toEqual(["✅ Пользователь 777 добавлен"]);
	});

	it("/add accepts a negative group ID", async () => {
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "/add -100123")));
		expect(await env.ALLOWED_USERS.get("-100123")).toBe("1");
	});

	it.each(["/add", "/add abc", "/add 1e5"])("%s → usage hint, nothing stored", async (text) => {
		await callWorker(makeRequest(makeMessage(ADMIN_ID, text)));
		expect((await env.ALLOWED_USERS.list()).keys).toEqual([]);
		expect(sentTexts()).toEqual(["❌ Укажи числовой ID: /add 123456"]);
	});

	it("/remove deletes the user", async () => {
		await env.ALLOWED_USERS.put("777", "1");
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "/remove 777")));
		expect(await env.ALLOWED_USERS.get("777")).toBeNull();
	});

	it.each(["/remove", "/remove abc"])("%s → usage hint", async (text) => {
		await callWorker(makeRequest(makeMessage(ADMIN_ID, text)));
		expect(sentTexts()).toEqual(["❌ Укажи числовой ID: /remove 123456"]);
	});

	it("/list shows stored users", async () => {
		await env.ALLOWED_USERS.put("777", "1");
		await callWorker(makeRequest(makeMessage(ADMIN_ID, "/list")));
		expect(sentTexts()).toEqual(["Разрешённые пользователи:\n777"]);
	});

	it("non-admin can't use admin commands", async () => {
		await env.ALLOWED_USERS.put("555", "1");
		await callWorker(makeRequest(makeMessage(555, "/add 777")));
		expect(await env.ALLOWED_USERS.get("777")).toBeNull();
	});
});
