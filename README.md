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
| **Rust (WASM)** | **~240 ms** | **~73** |

### Установка

Требования: Python 3.12+, [uv](https://docs.astral.sh/uv/).

Rust нужен только для Rust-воркеров: [rustup](https://rustup.rs) и `rustup target add wasm32-unknown-unknown`. Без него установка тоже пройдёт, но `pf create --type rust` работать не будет.

```bash
git clone https://github.com/AntonKoshuba/proxyflare.git
cd proxyflare
uv sync
uv tool install .
```

### Конфигурация

Создай `~/.config/proxyflare/.env` (шаблон: `.env.example`):

```env
PROXYFLARE_ACCOUNT_ID=your_cloudflare_account_id
PROXYFLARE_API_TOKEN=your_cloudflare_api_token
```

Команды работают из любой папки. Переменные окружения важнее файла, а `PROXYFLARE_CONFIG_DIR` меняет папку конфигурации. `.env` в текущей папке не читается.

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

# Задеплоить 5 воркеров (по умолчанию js)
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

Воркеры записываются в `~/.config/proxyflare/workers.json` с правами `600`: `pf create` дополняет файл, `pf delete` убирает из него удалённые. В файле лежат ключи воркеров: без `X-Proxyflare-Key` воркер отвечает 401. Поведение воркеров описано в [контракте](docs/worker-contract.md).

### Клиентская библиотека

```python
import httpx
from proxyflare.client import ProxyflareWorkersManager, AsyncProxyflareTransport
from proxyflare.paths import get_workers_file

manager = ProxyflareWorkersManager(get_workers_file())
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
CLOUDFLARE_API_TOKEN=your_token npx wrangler secret put WEBHOOK_SECRET
```

`WEBHOOK_SECRET` — случайная строка из символов `A-Z`, `a-z`, `0-9`, `_` и `-`, например результат `openssl rand -hex 32`. Без неё воркер отвечает 401 на все обновления.

Зарегистрируй вебхук с тем же секретом:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token \
WORKER_URL=https://telegram-md-bot.YOUR_SUBDOMAIN.workers.dev \
WEBHOOK_SECRET=your_secret \
npx tsx scripts/set-webhook.mts
```

### Использование

Просто отправь боту ссылку:

```
https://habr.com/ru/articles/123456/
```

Бот ответит `.md`-файлом с текстом статьи.

> Сайты за paywall (401) или с жёсткой защитой от ботов вернут ошибку.

---

## Команда `pf md`: URL → Markdown

Скачивает страницу через пул воркеров и сохраняет её как `.md`. Работает из любой папки.

```bash
pf md "https://habr.com/ru/articles/123456/"
```

Адрес бери в кавычки, иначе zsh споткнётся о `?` и `&`.

| Флаг | Назначение | По умолчанию |
|------|------------|--------------|
| `url` | Ссылка на статью (обязательный) | — |
| `-o, --output` | Папка сохранения | `articles/` в текущей папке |
| `--workers-file` | Файл воркеров | `~/.config/proxyflare/workers.json` |

- В начале файла идут метаданные: `title`, `source`, `saved`
- В stdout выводится только путь к файлу, сообщения идут в stderr
- Код возврата: `0` при успехе, `1` при ошибке, `2` при некорректном URL
- Если воркер не отвечает, запрос повторяется через другой, но не более 3 попыток
- Ошибки самого сайта, например 403 или 404, не повторяются
- Существующий файл не перезаписывается: новый получит суффикс `-2`, `-3` и так далее

> Иногда `trafilatura` принимает за статью один вложенный блок и отбрасывает остальное. Дело не в размере: страница RFC на 1159 КБ теряла 99% текста, а сгенерированная на 624 КБ сохранялась полностью. Если извлечено меньше 10% текста большой страницы, `pf md` сохранит весь текст без форматирования и предупредит об этом. Порог эвристический, на других страницах проблема может остаться незамеченной.

---

## Структура репозитория

```
proxyflare/
├── src/proxyflare/         # CLI и клиентская библиотека (Python)
│   ├── cli/                # Команды: create, delete, list, test, config, md
│   ├── client/             # httpx Transport + Workers Manager
│   ├── services/           # WorkerService (Cloudflare API), Tester
│   ├── workers/            # Исходники воркеров (js, rust)
│   └── models/             # Pydantic-модели
├── telegram-md-bot/        # Telegram-бот (TypeScript, Cloudflare Worker)
│   └── src/
│       ├── index.ts        # Обработчик вебхука
│       ├── scraper.ts      # Фетч и парсинг статей
│       └── telegram.ts     # Telegram Bot API
├── tests/                  # Unit, integration, e2e тесты
└── .env.example            # Шаблон конфигурации
```

---

## Лицензия

MIT
