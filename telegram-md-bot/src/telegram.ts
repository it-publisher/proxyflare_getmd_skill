export interface TelegramMessage {
	message_id: number;
	chat: { id: number };
	text?: string;
}

export interface TelegramUpdate {
	update_id: number;
	message?: TelegramMessage;
}

// The token is part of the request URL, so errors are built only from the method and the response
async function assertTelegramOk(method: string, response: Response): Promise<void> {
	if (response.ok) return;

	const body = await response
		.json<{ description?: string }>()
		.catch(() => null);
	const description = body?.description ?? "нет описания";
	throw new Error(`Telegram ${method}: HTTP ${response.status}, ${description}`);
}

export async function sendMessage(token: string, chatId: number, text: string): Promise<void> {
	const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ chat_id: chatId, text }),
	});
	await assertTelegramOk("sendMessage", response);
}

export async function sendDocument(
	token: string,
	chatId: number,
	filename: string,
	content: string
): Promise<void> {
	const form = new FormData();
	form.append("chat_id", String(chatId));
	form.append("document", new Blob([content], { type: "text/markdown" }), filename);

	const response = await fetch(`https://api.telegram.org/bot${token}/sendDocument`, {
		method: "POST",
		body: form,
	});
	await assertTelegramOk("sendDocument", response);
}
