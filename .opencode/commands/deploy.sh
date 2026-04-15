#!/bin/bash
# Deploy command for Telegram bot

set -e

echo "🚀 Deploying Telegram bot to Cloudflare Workers..."

# Check if we're in a Workers project
if [ ! -f "wrangler.toml" ]; then
    echo "❌ Error: wrangler.toml not found. Are you in a Workers project?"
    exit 1
fi

# Pre-deployment checks
echo "📋 Running pre-deployment checks..."

# Check TypeScript
echo "  ✓ Checking TypeScript..."
npm run check || npx tsc --noEmit

# Check linter
echo "  ✓ Running linter..."
npm run lint

# Check if secrets are configured
echo "  ✓ Checking secrets..."
npx wrangler secret list | grep -q "TELEGRAM_BOT_TOKEN" || {
    echo "❌ Error: TELEGRAM_BOT_TOKEN secret not found!"
    echo "   Run: npx wrangler secret put TELEGRAM_BOT_TOKEN"
    exit 1
}

# Confirm deployment
echo ""
read -p "Deploy to production? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

# Deploy
echo "📦 Deploying..."
npx wrangler deploy

# Get worker URL
echo ""
echo "✅ Deployment successful!"
echo ""
echo "📝 Next steps:"
echo ""
echo "1. Get your worker URL:"
echo "   npx wrangler deployments list"
echo ""
echo "2. Register webhook with Telegram:"
echo "   export TELEGRAM_BOT_TOKEN='your_token'"
echo "   export WORKER_URL='https://your-worker.workers.dev'"
echo "   curl -X POST \"https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/setWebhook\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d \"{\\\"url\\\": \\\"\${WORKER_URL}/webhook\\\"}\""
echo ""
echo "3. Verify webhook:"
echo "   curl \"https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/getWebhookInfo\""
echo ""
echo "4. Monitor logs:"
echo "   npx wrangler tail"
echo ""
echo "5. Test by sending a URL to your bot in Telegram"
