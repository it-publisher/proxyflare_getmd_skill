export interface TelegramMessage {
	message_id: number;
	chat: { id: number };
	text?: string;
}

export interface TelegramUpdate {
	update_id: number;
	message?: TelegramMessage;
}

export async function sendMessage(token: string, chatId: number, text: string): Promise<void> {
	await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ chat_id: chatId, text }),
	});
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

	await fetch(`https://api.telegram.org/bot${token}/sendDocument`, {
		method: "POST",
		body: form,
	});
}
