#!/bin/bash
# Debug command for Telegram bot

set -e

echo "🔍 Debugging Telegram bot..."

# Check if we're in a Workers project
if [ ! -f "wrangler.toml" ]; then
    echo "❌ Error: wrangler.toml not found. Are you in a Workers project?"
    exit 1
fi

# Check if TELEGRAM_BOT_TOKEN is set
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN not set in environment"
    echo "   Export it: export TELEGRAM_BOT_TOKEN='your_token'"
    echo ""
fi

# 1. Check bot status
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "1️⃣  Checking bot status..."
    BOT_INFO=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe")
    echo "$BOT_INFO" | jq '.' 2>/dev/null || echo "$BOT_INFO"
    
    if echo "$BOT_INFO" | grep -q '"ok":true'; then
        echo "   ✅ Bot is active"
    else
        echo "   ❌ Bot check failed"
    fi
    echo ""
fi

# 2. Check webhook status
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "2️⃣  Checking webhook status..."
    WEBHOOK_INFO=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo")
    echo "$WEBHOOK_INFO" | jq '.' 2>/dev/null || echo "$WEBHOOK_INFO"
    
    WEBHOOK_URL=$(echo "$WEBHOOK_INFO" | jq -r '.result.url' 2>/dev/null)
    PENDING_COUNT=$(echo "$WEBHOOK_INFO" | jq -r '.result.pending_update_count' 2>/dev/null)
    LAST_ERROR=$(echo "$WEBHOOK_INFO" | jq -r '.result.last_error_message' 2>/dev/null)
    
    if [ -n "$WEBHOOK_URL" ] && [ "$WEBHOOK_URL" != "null" ]; then
        echo "   ✅ Webhook registered: $WEBHOOK_URL"
    else
        echo "   ⚠️  No webhook registered"
    fi
    
    if [ -n "$PENDING_COUNT" ] && [ "$PENDING_COUNT" != "null" ] && [ "$PENDING_COUNT" != "0" ]; then
        echo "   ⚠️  Pending updates: $PENDING_COUNT"
    fi
    
    if [ -n "$LAST_ERROR" ] && [ "$LAST_ERROR" != "null" ]; then
        echo "   ❌ Last error: $LAST_ERROR"
    fi
    echo ""
fi

# 3. Check secrets
echo "3️⃣  Checking secrets..."
SECRETS=$(npx wrangler secret list 2>/dev/null)
if echo "$SECRETS" | grep -q "TELEGRAM_BOT_TOKEN"; then
    echo "   ✅ TELEGRAM_BOT_TOKEN secret configured"
else
    echo "   ❌ TELEGRAM_BOT_TOKEN secret not found"
    echo "      Run: npx wrangler secret put TELEGRAM_BOT_TOKEN"
fi
echo ""

# 4. Check wrangler.toml configuration
echo "4️⃣  Checking wrangler.toml..."
if grep -q "ALLOWED_CHAT_ID" wrangler.toml; then
    ALLOWED_CHAT_ID=$(grep ALLOWED_CHAT_ID wrangler.toml | cut -d'"' -f2)
    echo "   ✅ ALLOWED_CHAT_ID: $ALLOWED_CHAT_ID"
else
    echo "   ❌ ALLOWED_CHAT_ID not found in wrangler.toml"
fi

if grep -q "PROXY_WORKERS" wrangler.toml; then
    echo "   ✅ PROXY_WORKERS configured"
else
    echo "   ⚠️  PROXY_WORKERS not found in wrangler.toml"
fi
echo ""

# 5. Check deployments
echo "5️⃣  Checking deployments..."
DEPLOYMENTS=$(npx wrangler deployments list 2>/dev/null | head -5)
if [ -n "$DEPLOYMENTS" ]; then
    echo "$DEPLOYMENTS"
else
    echo "   ⚠️  No deployments found"
fi
echo ""

# 6. Check local .dev.vars
echo "6️⃣  Checking local configuration..."
if [ -f ".dev.vars" ]; then
    echo "   ✅ .dev.vars exists (for local testing)"
else
    echo "   ⚠️  .dev.vars not found"
    echo "      Create it: echo 'TELEGRAM_BOT_TOKEN=your_token' > .dev.vars"
fi
echo ""

# 7. Offer to tail logs
echo "7️⃣  Live logs"
read -p "Start live log monitoring? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📊 Starting log tail... (Ctrl+C to stop)"
    echo "   Send a message to your bot to see logs"
    echo ""
    npx wrangler tail
fi

echo ""
echo "🔧 Troubleshooting tips:"
echo ""
echo "If bot doesn't respond:"
echo "  1. Check webhook is registered: curl \"https://api.telegram.org/bot\$TELEGRAM_BOT_TOKEN/getWebhookInfo\""
echo "  2. Check ALLOWED_CHAT_ID matches your chat ID"
echo "  3. Check logs: npx wrangler tail"
echo "  4. Test locally: npx wrangler dev"
echo ""
echo "If parsing fails:"
echo "  1. Check proxy workers are accessible"
echo "  2. Try different URL"
echo "  3. Check logs for specific error"
echo ""
echo "If deployment fails:"
echo "  1. Check TypeScript: npm run check"
echo "  2. Check secrets: npx wrangler secret list"
echo "  3. Check account: npx wrangler whoami"
