import { sendMessage, sendDocument } from "./telegram";
import type { TelegramUpdate } from "./telegram";
import { extractUrl, fetchHtml, parseArticle, slugify } from "./scraper";

export interface Env {
	TELEGRAM_BOT_TOKEN: string;
	ALLOWED_CHAT_ID: string;
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

		if (String(chatId) !== env.ALLOWED_CHAT_ID) {
			return new Response("OK", { status: 200 });
		}

		const text = message.text?.trim();
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
			const html = await fetchHtml(url);
			const { title, markdown } = parseArticle(html, url);
			const filename = `${slugify(title)}.md`;

			await sendDocument(env.TELEGRAM_BOT_TOKEN, chatId, filename, markdown);
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			await sendMessage(env.TELEGRAM_BOT_TOKEN, chatId, `❌ Ошибка: ${msg}`);
		}

		return new Response("OK", { status: 200 });
	},
} satisfies ExportedHandler<Env>;
