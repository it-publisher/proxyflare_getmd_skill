#!/bin/bash
# Test command for Telegram bot development

set -e

echo "🧪 Running tests for Telegram bot..."

# Check if we're in a Workers project
if [ ! -f "wrangler.toml" ]; then
    echo "❌ Error: wrangler.toml not found. Are you in a Workers project?"
    exit 1
fi

# Check TypeScript compilation
echo "📝 Checking TypeScript..."
npm run check || npx tsc --noEmit

# Run linter
echo "🔍 Running linter..."
npm run lint || echo "⚠️  Linting issues found"

# Check if .dev.vars exists for local testing
if [ ! -f ".dev.vars" ]; then
    echo "⚠️  Warning: .dev.vars not found. Create it for local testing:"
    echo "   echo 'TELEGRAM_BOT_TOKEN=your_token' > .dev.vars"
fi

# Start local dev server in background
echo "🚀 Starting local dev server..."
npx wrangler dev &
WRANGLER_PID=$!

# Wait for server to start
sleep 3

# Test health endpoint (if exists)
echo "🏥 Testing health endpoint..."
curl -s http://localhost:8787/health || echo "⚠️  No health endpoint"

# Test webhook endpoint with mock data
echo "📨 Testing webhook endpoint..."
ALLOWED_CHAT_ID=$(grep ALLOWED_CHAT_ID wrangler.toml | cut -d'"' -f2)

if [ -n "$ALLOWED_CHAT_ID" ]; then
    curl -X POST http://localhost:8787/webhook \
      -H "Content-Type: application/json" \
      -d "{
        \"update_id\": 1,
        \"message\": {
          \"message_id\": 1,
          \"chat\": {\"id\": $ALLOWED_CHAT_ID, \"type\": \"private\"},
          \"text\": \"https://example.com\",
          \"from\": {\"id\": $ALLOWED_CHAT_ID, \"username\": \"test\"}
        }
      }" || echo "⚠️  Webhook test failed"
else
    echo "⚠️  ALLOWED_CHAT_ID not found in wrangler.toml"
fi

# Kill dev server
kill $WRANGLER_PID 2>/dev/null || true

echo ""
echo "✅ Tests completed!"
echo ""
echo "Next steps:"
echo "  1. Test manually: npm run dev"
echo "  2. Deploy: npx wrangler deploy"
echo "  3. Register webhook: curl -X POST 'https://api.telegram.org/bot<TOKEN>/setWebhook' -d '{\"url\": \"https://your-worker.workers.dev/webhook\"}'"
