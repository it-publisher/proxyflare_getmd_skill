# OpenCode Configuration for Telegram Bot Project

This directory contains specialized skills, rules, agents, and commands for developing a Telegram bot on Cloudflare Workers.

## Structure

```
.opencode/
├── skills/                          # Specialized knowledge domains
│   ├── telegram-bot-dev.md         # Telegram Bot API patterns
│   ├── web-scraping-parsing.md     # Readability + Turndown
│   └── cloudflare-workers.md       # Workers development
├── agents/                          # Specialized task agents
│   ├── telegram-bot-debugger.md    # Debugging workflows
│   └── cloudflare-deployment.md    # Deployment automation
├── commands/                        # CLI commands
│   ├── test.sh                     # Run tests
│   ├── deploy.sh                   # Deploy to production
│   ├── commit.sh                   # Structured commits
│   └── debug.sh                    # Debug bot issues
└── rules.md                        # Project-specific rules
```

## Skills

### telegram-bot-dev.md
Telegram Bot API best practices, webhook patterns, security, error handling.

**Use when:**
- Implementing webhook handlers
- Working with Telegram API methods
- Handling bot security and validation

### web-scraping-parsing.md
Web scraping with @mozilla/readability and HTML to Markdown conversion with turndown.

**Use when:**
- Parsing web pages
- Converting HTML to Markdown
- Handling different site structures

### cloudflare-workers.md
Cloudflare Workers development, Wrangler CLI, deployment, monitoring.

**Use when:**
- Setting up Workers projects
- Managing secrets and environment variables
- Deploying and monitoring workers

## Agents

### telegram-bot-debugger.md
Diagnostic workflows for troubleshooting bot issues.

**Use when:**
- Bot not responding
- Webhook issues
- Parsing failures
- API errors

### cloudflare-deployment.md
Automated deployment workflows and environment management.

**Use when:**
- First deployment
- Managing multiple environments
- Rolling back versions
- CI/CD setup

## Commands

### test.sh
Runs pre-deployment checks: TypeScript compilation, linting, local server testing.

```bash
.opencode/commands/test.sh
```

### deploy.sh
Deploys to Cloudflare Workers with pre-deployment validation and post-deployment instructions.

```bash
.opencode/commands/deploy.sh
```

### commit.sh
Interactive commit helper with conventional commit format and pre-commit checks.

```bash
.opencode/commands/commit.sh
```

### debug.sh
Comprehensive debugging tool: checks bot status, webhook, secrets, deployments, and live logs.

```bash
.opencode/commands/debug.sh
```

## Rules

`rules.md` contains project-specific coding standards, security practices, and workflows:

- TypeScript and code style guidelines
- Security rules (secrets, validation, error handling)
- Telegram API best practices
- Proxy and parsing patterns
- Performance optimization
- Testing and deployment checklists
- Git workflow conventions

## Usage

### For AI Assistant
When working on this project, the AI assistant should:
1. Load relevant skills based on the task
2. Follow rules.md guidelines
3. Use agents for specialized workflows
4. Reference commands for common operations

### For Developers
```bash
# Run tests before committing
.opencode/commands/test.sh

# Make a structured commit
.opencode/commands/commit.sh

# Deploy to production
.opencode/commands/deploy.sh

# Debug issues
.opencode/commands/debug.sh
```

## Environment Setup

### Required Secrets
```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
```

### Local Development
```bash
# Create .dev.vars for local testing
echo "TELEGRAM_BOT_TOKEN=your_token_here" > .dev.vars
```

### Configuration
Edit `wrangler.toml`:
```toml
[vars]
ALLOWED_CHAT_ID = "your_chat_id"
PROXY_WORKERS = ["https://proxy1.workers.dev", ...]
```

## Quick Start

1. **Initialize project:**
   ```bash
   npm create cloudflare@latest telegram-md-bot
   ```

2. **Configure:**
   - Add secrets: `npx wrangler secret put TELEGRAM_BOT_TOKEN`
   - Edit `wrangler.toml` with your settings

3. **Develop:**
   ```bash
   npm run dev
   ```

4. **Test:**
   ```bash
   .opencode/commands/test.sh
   ```

5. **Deploy:**
   ```bash
   .opencode/commands/deploy.sh
   ```

6. **Debug:**
   ```bash
   .opencode/commands/debug.sh
   ```

## Contributing

When adding new skills, agents, or commands:
- Follow existing structure and format
- Include clear "When to use" sections
- Provide code examples
- Add troubleshooting sections
- Update this README

## Notes

- All commands are executable shell scripts
- Skills and agents are Markdown documentation
- Rules apply to all code in the project
- Commands require bash and standard Unix tools
