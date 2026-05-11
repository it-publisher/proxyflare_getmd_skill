# Proxyflare

![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen.svg)

Инструментарий для работы с Cloudflare Workers как прокси-сетью. Два компонента:

- **Proxyflare CLI** — Python-утилита для деплоя и управления пулом прокси-воркеров
- **telegram-md-bot** — Telegram-бот, который принимает URL статей и возвращает `.md`-файл

---

## Proxyflare CLI

### Что делает

Разворачивает десятки прокси-воркеров на Cloudflare Workers одной командой. Каждый воркер принимает целевой URL и проксирует запрос — через query-параметр, заголовок или путь.

Поддерживаемые типы воркеров:

| Тип | Latency (avg) | RPS |
|-----|--------------|-----|
| JavaScript | ~425 ms | ~43 |
| Python (Pyodide) | ~410 ms | ~46 |
| **Rust (WASM)** | **~240 ms** | **~73** |

### Установка

Требования: Python 3.12+, [uv](https://docs.astral.sh/uv/), Rust + cargo (для Rust-воркеров)

```bash
git clone https://github.com/AntonKoshuba/proxyflare.git
cd proxyflare
uv sync
uv tool install .
```

### Конфигурация

Создай `.env` в корне проекта (см. `.env.example`):

```env
PROXYFLARE_ACCOUNT_ID=your_cloudflare_account_id
PROXYFLARE_API_TOKEN=your_cloudflare_api_token
```

#### Требования к API-токену

В Cloudflare Dashboard → My Profile → API Tokens → Create Token (Custom):

- **User → User Details → Read**
- **User → Memberships → Read**
- **Account → Workers Scripts → Edit**
- **Account → Account Settings → Read**

Оставь Account Resources и Zone Resources как **Include → All**.

### Команды

```bash
# Проверить конфигурацию и права токена
pf config verify

# Задеплоить 5 воркеров (по умолчанию python)
pf create --count 5

# Задеплоить rust-воркеры
pf create --count 3 --type rust

# Список активных воркеров
pf list

# Удалить все воркеры
pf delete --all

# Протестировать пул
pf test --url https://example.com
```

Результаты деплоя сохраняются в `proxyflare-workers.json` (в `.gitignore`).

### Клиентская библиотека

```python
import httpx
from proxyflare.client import ProxyflareWorkersManager, AsyncProxyflareTransport

manager = ProxyflareWorkersManager.from_file("proxyflare-workers.json")
transport = AsyncProxyflareTransport(manager)

async with httpx.AsyncClient(transport=transport) as client:
    response = await client.get("https://example.com")
```

---

## telegram-md-bot

### Что делает

Telegram-бот на Cloudflare Workers. Пришли ему ссылку — получишь `.md`-файл с текстом статьи.

Использует Readability для извлечения контента и node-html-markdown для конвертации.

### Деплой

Требования: Node.js 18+, аккаунт Cloudflare

```bash
cd telegram-md-bot
npm install
```

Создай бота через [@BotFather](https://t.me/BotFather), получи токен.
Узнай свой chat ID через [@userinfobot](https://t.me/userinfobot).

Настрой `wrangler.jsonc` — укажи свой `account_id`:

```jsonc
{
  "account_id": "your_cloudflare_account_id",
  ...
}
```

Задеплой воркер:

```bash
CLOUDFLARE_API_TOKEN=your_token npx wrangler deploy
```

Установи секреты:

```bash
CLOUDFLARE_API_TOKEN=your_token npx wrangler secret put TELEGRAM_BOT_TOKEN
CLOUDFLARE_API_TOKEN=your_token npx wrangler secret put ALLOWED_CHAT_ID
```

Зарегистрируй вебхук:

```bash
curl "https://api.telegram.org/botYOUR_TOKEN/setWebhook?url=https://telegram-md-bot.YOUR_SUBDOMAIN.workers.dev"
```

### Использование

Просто отправь боту ссылку:

```
https://habr.com/ru/articles/123456/
```

Бот ответит `.md`-файлом с текстом статьи.

> Сайты за paywall (401) или с жёсткой защитой от ботов вернут ошибку.

---

## Структура репозитория

```
proxyflare/
├── src/proxyflare/         # CLI и клиентская библиотека (Python)
│   ├── cli/                # Команды: create, delete, list, test, config
│   ├── client/             # httpx Transport + Workers Manager
│   ├── services/           # WorkerService (Cloudflare API), Tester
│   ├── workers/            # Исходники воркеров (py, js, rust)
│   └── models/             # Pydantic-модели
├── telegram-md-bot/        # Telegram-бот (TypeScript, Cloudflare Worker)
│   └── src/
│       ├── index.ts        # Обработчик вебхука
│       ├── scraper.ts      # Фетч и парсинг статей
│       └── telegram.ts     # Telegram Bot API
├── tests/                  # Unit, integration, e2e тесты
├── web_to_md.py            # Standalone-скрипт: URL → Markdown через CLI
└── .env.example            # Шаблон конфигурации
```

---

## Лицензия

MIT
