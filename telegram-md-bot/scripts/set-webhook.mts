// Usage: TELEGRAM_BOT_TOKEN=<token> WORKER_URL=<url> WEBHOOK_SECRET=<secret> npx tsx scripts/set-webhook.mts
// WEBHOOK_SECRET must match the worker secret of the same name.
const token = process.env.TELEGRAM_BOT_TOKEN;
const workerUrl = process.env.WORKER_URL;
const webhookSecret = process.env.WEBHOOK_SECRET;

if (!token || !workerUrl || !webhookSecret) {
	console.error("Required: TELEGRAM_BOT_TOKEN, WORKER_URL and WEBHOOK_SECRET");
	process.exit(1);
}

if (!/^[A-Za-z0-9_-]{1,256}$/.test(webhookSecret)) {
	console.error("WEBHOOK_SECRET must be 1-256 characters: A-Z, a-z, 0-9, _ and -");
	process.exit(1);
}

const res = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({ url: `${workerUrl}/webhook`, secret_token: webhookSecret }),
});

const data = await res.json();
console.log(data);

if (!res.ok) process.exit(1);
