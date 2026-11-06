import { sendMessage, sendDocument } from "./telegram";
import type { TelegramMessage, TelegramUpdate } from "./telegram";
import { extractUrl, fetchContent, parseArticle, slugify } from "./scraper";
import type { ParsedArticle } from "./scraper";

export interface Env {
	TELEGRAM_BOT_TOKEN: string;
	ALLOWED_CHAT_ID: string;
	WEBHOOK_SECRET: string;
	ALLOWED_USERS: KVNamespace;
	JINA_API_KEY?: string;
}

const WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token";
const CHAT_ID_PATTERN = /^-?\d+$/;

function isValidWebhookSecret(request: Request, expectedSecret?: string): boolean {
	const providedSecret = request.headers.get(WEBHOOK_SECRET_HEADER);
	if (!expectedSecret || !providedSecret) return false;

	const encoder = new TextEncoder();
	const provided = encoder.encode(providedSecret);
	const expected = encoder.encode(expectedSecret);
	return (
		provided.byteLength === expected.byteLength &&
		crypto.subtle.timingSafeEqual(provided, expected)
	);
}

async function isAllowed(env: Env, chatId: number): Promise<boolean> {
	if (isAdmin(env, chatId)) return true;
	const entry = await env.ALLOWED_USERS.get(String(chatId));
	return entry !== null;
}

function isAdmin(env: Env, chatId: number): boolean {
	return String(chatId) === env.ALLOWED_CHAT_ID;
}

async function addUser(env: Env, chatId: number, userId?: string): Promise<void> {
	if (!userId || !CHAT_ID_PATTERN.test(userId)) {
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "❌ Укажи числовой ID: /add 123456");
		return;
	}
	await env.ALLOWED_USERS.put(userId, "1");
	await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `✅ Пользователь ${userId} добавлен`);
}

async function removeUser(env: Env, chatId: number, userId?: string): Promise<void> {
	if (!userId || !CHAT_ID_PATTERN.test(userId)) {
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "❌ Укажи числовой ID: /remove 123456");
		return;
	}
	await env.ALLOWED_USERS.delete(userId);
	await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `✅ Пользователь ${userId} удалён`);
}

async function listUsers(env: Env, chatId: number): Promise<void> {
	const list = await env.ALLOWED_USERS.list();
	const ids = list.keys.map((key) => key.name).join("\n");
	const reply = ids ? `Разрешённые пользователи:\n${ids}` : "Список пуст";
	await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, reply);
}

/** Returns true when the text was an admin command and needs no further handling. */
async function handleAdminCommand(env: Env, chatId: number, text: string): Promise<boolean> {
	const [command, argument] = text.split(/\s+/);
	switch (command) {
		case "/add":
			await addUser(env, chatId, argument);
			return true;
		case "/remove":
			await removeUser(env, chatId, argument);
			return true;
		case "/list":
			await listUsers(env, chatId);
			return true;
		default:
			return false;
	}
}

async function loadArticle(url: string, jinaApiKey?: string): Promise<ParsedArticle> {
	const { content, isMarkdown } = await fetchContent(url, jinaApiKey);
	if (!isMarkdown) return parseArticle(content, url);

	const titleMatch = content.match(/^#\s+(.+)$/m);
	const title = titleMatch
		? titleMatch[1]
		: new URL(url).pathname.split("/").filter(Boolean).pop() ?? "article";
	return { title, markdown: content };
}

async function sendArticle(env: Env, chatId: number, url: string): Promise<void> {
	try {
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `⏳ Скачиваю: ${url}`);
		const { title, markdown } = await loadArticle(url, env.JINA_API_KEY);
		await sendDocument(env.TELEGRAM_BOT_TOKEN, chatId, `${slugify(title)}.md`, markdown);
	} catch (err) {
		const errorMessage = err instanceof Error ? err.message : String(err);
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `❌ Ошибка: ${errorMessage}`);
	}
}

async function handleMessage(env: Env, message: TelegramMessage): Promise<void> {
	const chatId = message.chat.id;
	const text = message.text?.trim() ?? "";

	if (isAdmin(env, chatId) && (await handleAdminCommand(env, chatId, text))) return;
	if (!(await isAllowed(env, chatId))) return;

	if (!text) {
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "Отправь ссылку на статью.");
		return;
	}

	const url = extractUrl(text);
	if (!url) {
		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "Не нашёл URL в сообщении.");
		return;
	}

	await sendArticle(env, chatId, url);
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		if (request.method !== "POST") {
			return new Response("OK", { status: 200 });
		}

		if (!isValidWebhookSecret(request, env.WEBHOOK_SECRET)) {
			return new Response("Unauthorized", { status: 401 });
		}

		let update: TelegramUpdate;
		try {
			update = await request.json() as TelegramUpdate;
		} catch {
			return new Response("Bad Request", { status: 400 });
		}

		if (update.message) {
			try {
				await handleMessage(env, update.message);
			} catch (err) {
				console.error("Failed to handle Telegram update", update.update_id, err);
			}
		}

		// Any other status makes Telegram redeliver the update, and a retry would repeat the same failure
		return new Response("OK", { status: 200 });
	},
} satisfies ExportedHandler<Env>;
