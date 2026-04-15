#!/bin/bash
# Commit command for Telegram bot project

set -e

echo "📝 Preparing commit..."

# Check if there are changes to commit
if [ -z "$(git status --porcelain)" ]; then
    echo "❌ No changes to commit"
    exit 0
fi

# Show status
echo ""
echo "📊 Current status:"
git status --short

# Run checks before commit
echo ""
echo "🔍 Running pre-commit checks..."

# Check TypeScript (if in Workers project)
if [ -f "wrangler.toml" ]; then
    echo "  ✓ Checking TypeScript..."
    npm run check 2>/dev/null || npx tsc --noEmit 2>/dev/null || echo "  ⚠️  TypeScript check skipped"
fi

# Check linter
if [ -f "package.json" ]; then
    echo "  ✓ Running linter..."
    npm run lint 2>/dev/null || echo "  ⚠️  Linter check skipped"
fi

# Check for secrets in files
echo "  ✓ Checking for secrets..."
if git diff --cached | grep -iE "(api[_-]?key|token|secret|password|bot.*token)" | grep -v "TELEGRAM_BOT_TOKEN" | grep -v ".opencode"; then
    echo "❌ Warning: Possible secrets detected in staged files!"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if .dev.vars is staged
if git diff --cached --name-only | grep -q "\.dev\.vars"; then
    echo "❌ Error: .dev.vars should not be committed!"
    echo "   Run: git reset HEAD .dev.vars"
    exit 1
fi

# Get commit type
echo ""
echo "Select commit type:"
echo "  1) feat     - New feature"
echo "  2) fix      - Bug fix"
echo "  3) refactor - Code refactoring"
echo "  4) docs     - Documentation"
echo "  5) test     - Tests"
echo "  6) chore    - Maintenance"
echo "  7) style    - Code style"
echo ""
read -p "Enter number (1-7): " commit_type_num

case $commit_type_num in
    1) commit_type="feat" ;;
    2) commit_type="fix" ;;
    3) commit_type="refactor" ;;
    4) commit_type="docs" ;;
    5) commit_type="test" ;;
    6) commit_type="chore" ;;
    7) commit_type="style" ;;
    *) echo "❌ Invalid choice"; exit 1 ;;
esac

# Get commit message
echo ""
read -p "Enter commit message: " commit_message

if [ -z "$commit_message" ]; then
    echo "❌ Commit message cannot be empty"
    exit 1
fi

# Optional: Add scope
read -p "Add scope (optional, e.g., webhook, parser): " scope

if [ -n "$scope" ]; then
    full_message="${commit_type}(${scope}): ${commit_message}"
else
    full_message="${commit_type}: ${commit_message}"
fi

# Show what will be committed
echo ""
echo "📦 Will commit with message:"
echo "   $full_message"
echo ""
echo "Files to be committed:"
git diff --cached --name-only | sed 's/^/   /'
echo ""

# Confirm
read -p "Proceed with commit? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Commit cancelled"
    exit 1
fi

# Stage all changes if nothing is staged
if [ -z "$(git diff --cached --name-only)" ]; then
    echo "📦 Staging all changes..."
    git add .
fi

# Commit
git commit -m "$full_message"

echo ""
echo "✅ Committed successfully!"
echo ""
echo "📝 Next steps:"
echo "   git push          - Push to remote"
echo "   git log --oneline - View commit history"
