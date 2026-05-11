// Usage: TELEGRAM_BOT_TOKEN=<token> WORKER_URL=<url> npx tsx scripts/set-webhook.ts
const token = process.env.TELEGRAM_BOT_TOKEN;
const workerUrl = process.env.WORKER_URL;

if (!token || !workerUrl) {
	console.error("Required: TELEGRAM_BOT_TOKEN and WORKER_URL");
	process.exit(1);
}

const res = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({ url: `${workerUrl}/webhook` }),
});

const data = await res.json();
console.log(data);
