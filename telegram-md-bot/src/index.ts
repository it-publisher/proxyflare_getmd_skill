import { sendMessage, sendDocument } from "./telegram";
import type { TelegramUpdate } from "./telegram";
import { extractUrl, fetchContent, parseArticle, slugify } from "./scraper";

export interface Env {
	TELEGRAM_BOT_TOKEN: string;
	ALLOWED_CHAT_ID: string;
	ALLOWED_USERS: KVNamespace;
	JINA_API_KEY?: string;
}

async function isAllowed(env: Env, chatId: number): Promise<boolean> {
	if (String(chatId) === env.ALLOWED_CHAT_ID) return true;
	const entry = await env.ALLOWED_USERS.get(String(chatId));
	return entry !== null;
}

function isAdmin(env: Env, chatId: number): boolean {
	return String(chatId) === env.ALLOWED_CHAT_ID;
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		if (request.method !== "POST") {
			return new Response("OK", { status: 200 });
		}

		let update: TelegramUpdate;
		try {
			update = await request.json() as TelegramUpdate;
		} catch {
			return new Response("Bad Request", { status: 400 });
		}

		const message = update.message;
		if (!message) return new Response("OK", { status: 200 });

		const chatId = message.chat.id;
		const text = message.text?.trim() ?? "";

		// Admin commands
		if (isAdmin(env, chatId)) {
			if (text.startsWith("/add ")) {
				const id = text.slice(5).trim();
				if (!id || isNaN(Number(id))) {
					await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "❌ Укажи числовой ID: /add 123456");
					return new Response("OK", { status: 200 });
				}
				await env.ALLOWED_USERS.put(id, "1");
				await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `✅ Пользователь ${id} добавлен`);
				return new Response("OK", { status: 200 });
			}

			if (text.startsWith("/remove ")) {
				const id = text.slice(8).trim();
				await env.ALLOWED_USERS.delete(id);
				await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `✅ Пользователь ${id} удалён`);
				return new Response("OK", { status: 200 });
			}

			if (text === "/list") {
				const list = await env.ALLOWED_USERS.list();
				const ids = list.keys.map((k) => k.name).join("\n");
				const reply = ids ? `Разрешённые пользователи:\n${ids}` : "Список пуст";
				await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, reply);
				return new Response("OK", { status: 200 });
			}
		}

		// Auth check
		if (!(await isAllowed(env, chatId))) {
			return new Response("OK", { status: 200 });
		}

		if (!text) {
			await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "Отправь ссылку на статью.");
			return new Response("OK", { status: 200 });
		}

		const url = extractUrl(text);
		if (!url) {
			await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, "Не нашёл URL в сообщении.");
			return new Response("OK", { status: 200 });
		}

		await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `⏳ Скачиваю: ${url}`);

		try {
			const { content, isMarkdown } = await fetchContent(url, env.JINA_API_KEY);
			let title: string;
			let markdown: string;

			if (isMarkdown) {
				const titleMatch = content.match(/^#\s+(.+)$/m);
				title = titleMatch
					? titleMatch[1]
					: new URL(url).pathname.split("/").filter(Boolean).pop() ?? "article";
				markdown = content;
			} else {
				({ title, markdown } = parseArticle(content, url));
			}

			const filename = `${slugify(title)}.md`;
			await sendDocument(env.TELEGRAM_BOT_TOKEN, chatId, filename, markdown);
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `❌ Ошибка: ${msg}`);
		}

		return new Response("OK", { status: 200 });
	},
} satisfies ExportedHandler<Env>;
