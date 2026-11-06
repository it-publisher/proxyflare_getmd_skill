# Proxyflare

![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
[![CI](https://github.com/it-publisher/proxyflare_getmd_skill/actions/workflows/ci.yml/badge.svg)](https://github.com/it-publisher/proxyflare_getmd_skill/actions/workflows/ci.yml)

Инструменты для работы с Cloudflare Workers как с сетью прокси и для сохранения статей в Markdown.

| Компонент | Что делает |
|-----------|------------|
| `pf` | CLI: разворачивает пул прокси-воркеров и управляет им |
| `pf md` | Скачивает статью через пул и сохраняет как `.md` |
| Клиентская библиотека | httpx-транспорт, отправляющий запросы через пул |
| `telegram-md-bot` | Telegram-бот: присылаешь ссылку, получаешь `.md`-файл. Не использует пул |

Основано на [FlareProx](https://github.com/MrTurvey/flareprox).

---

## Установка

Требования: Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/it-publisher/proxyflare_getmd_skill.git
cd proxyflare_getmd_skill
uv tool install .
```

Rust нужен только для Rust-воркеров. Без него установка тоже пройдёт, но `pf create --type rust` работать не будет:

```bash
rustup target add wasm32-unknown-unknown
uv tool install --force .
```

### Настройка

Создай `~/.config/proxyflare/.env` (шаблон: `.env.example`) и закрой его от других пользователей:

```bash
mkdir -p -m 700 ~/.config/proxyflare
cp .env.example ~/.config/proxyflare/.env
chmod 600 ~/.config/proxyflare/.env
```

```env
PROXYFLARE_ACCOUNT_ID=your_cloudflare_account_id
PROXYFLARE_API_TOKEN=your_cloudflare_api_token
```

- Команды работают из любой папки, `.env` в текущей папке не читается
- Переменные окружения важнее файла
- `PROXYFLARE_CONFIG_DIR` меняет папку конфигурации

### API-токен

Cloudflare Dashboard → My Profile → API Tokens → Create Token. Шаблон **Edit Cloudflare Workers** подходит и для `pf`, и для деплоя бота.

Для одного только `pf` достаточно своего токена (Custom) с правами:

- User → User Details → Read
- User → Memberships → Read
- Account → Workers Scripts → Edit
- Account → Account Settings → Read

`pf config verify` проверит токен. Предупреждение `Could not fetch permissions` означает лишь, что токен не может прочитать собственные права, и работе не мешает.

---

## Команды `pf`

```bash
pf config verify                     # Проверить конфигурацию и токен
pf config show                       # Показать настройки и пути к файлам

pf create --count 5                  # Задеплоить 5 JS-воркеров
pf create --count 3 --type rust      # Задеплоить Rust-воркеры
pf list                              # Список воркеров на аккаунте

pf test                              # По одному запросу через каждый воркер
pf test --url https://example.com --limit 10

pf delete proxyflare-123-abc         # Удалить один воркер
pf delete --all                      # Удалить все воркеры с префиксом proxyflare-

pf md "https://example.com/article"  # Сохранить статью в Markdown
```

Коды возврата: `0` при успехе, `1` при ошибке, в том числе частичной, например если не удалось удалить часть воркеров, `2` при некорректных аргументах.

### Типы воркеров

| Тип | Сборка | Latency (avg) | RPS |
|-----|--------|---------------|-----|
| JavaScript (по умолчанию) | Не нужна | ~425 ms | ~43 |
| Rust (WASM) | Нужен Rust | ~240 ms | ~73 |

⚠️ Цифры взяты из старых замеров, с тех пор воркеры изменились. Как замерить самому, описано в разделе [Разработка](#разработка).

### Файл воркеров

Воркеры записываются в `~/.config/proxyflare/workers.json`:

- `pf create` дополняет файл, а если файл повреждён, отказывается деплоить
- `pf delete` убирает удалённые воркеры, неудачно удалённые остаются
- В файле лежат ключи воркеров, поэтому он доступен только владельцу (права `600`)
- Файл из версий до 0.2.0 не читается: удали старые воркеры, файл и создай новые

### Как работают воркеры

Каждый воркер принимает целевой URL через query-параметр, заголовок или путь и отвечает только на запросы с верным заголовком `X-Proxyflare-Key`. Точное поведение описано в [контракте](docs/worker-contract.md).

---

## `pf md`: URL → Markdown

```bash
pf md "https://habr.com/ru/articles/123456/"
```

Адрес бери в кавычки, иначе zsh споткнётся о `?` и `&`.

| Аргумент | Назначение | По умолчанию |
|----------|------------|--------------|
| `url` | Ссылка на статью | Обязательный |
| `-o, --output` | Папка сохранения | `articles/` в текущей папке |
| `--workers-file` | Файл воркеров | `~/.config/proxyflare/workers.json` |

- В начале файла идут метаданные: `title`, `source`, `saved`
- В stdout выводится только путь к файлу, сообщения идут в stderr
- Если воркер не отвечает, запрос повторяется через другой, но не более 3 попыток
- Ошибки самого сайта, например 403 или 404, не повторяются
- Существующий файл не перезаписывается: новый получит суффикс `-2`, `-3` и так далее

⚠️ Иногда `trafilatura` принимает за статью один вложенный блок и отбрасывает остальное. Дело не в размере: страница RFC на 1159 КБ теряла 99% текста, а сгенерированная на 624 КБ сохранялась полностью. Если извлечено меньше 10% текста большой страницы, `pf md` сохранит весь текст без форматирования и предупредит об этом. Порог подобран на трёх страницах, менее заметные потери останутся незамеченными.

---

## Клиентская библиотека

```python
import httpx

from proxyflare.client import AsyncProxyflareTransport, ProxyflareWorkersManager
from proxyflare.paths import get_workers_file

manager = ProxyflareWorkersManager(get_workers_file())
transport = AsyncProxyflareTransport(manager)

async with httpx.AsyncClient(transport=transport) as client:
    response = await client.get("https://example.com")
```

Есть и синхронный `ProxyflareTransport`. Каждый запрос идёт через случайный воркер из пула.

---

## Что видит сайт

Прокси скрывает твой IP от сайта, но не делает запрос неотличимым от обычного:

- **`CF-Worker`:** Cloudflare добавляет этот заголовок с именем воркера или поддоменом, и убрать его нельзя. Сайт легко может опознать такой запрос и заблокировать его
- **`X-Forwarded-For`:** воркер подставляет случайный IP или значение из `X-My-X-Forwarded-For`
- **`User-Agent`:** `pf md` представляется браузером Chrome

Ответственность за использование на тебе: соблюдай условия Cloudflare и условия сайтов, к которым обращаешься.

---

## telegram-md-bot

Telegram-бот на Cloudflare Workers. Статью извлекает Readability, в Markdown переводит node-html-markdown.

Если сайт отвечает 403 или 429, бот скачивает страницу через сервис [Jina Reader](https://r.jina.ai). ⚠️ В этом случае адрес страницы уходит стороннему сервису.

### Деплой

Требования: Node.js 22+, аккаунт Cloudflare, токен (см. [API-токен](#api-токен)).

1. Создай бота через [@BotFather](https://t.me/BotFather) и узнай свой chat ID через [@userinfobot](https://t.me/userinfobot).
2. Установи зависимости и задай доступ к Cloudflare:

   ```bash
   cd telegram-md-bot
   npm install
   read -s "CLOUDFLARE_API_TOKEN?Токен Cloudflare: "; echo
   export CLOUDFLARE_API_TOKEN
   ```

   Строку с `read` вводи отдельно, а не блоком: иначе она примет за токен следующую строку. Если у токена несколько аккаунтов, задай ещё `CLOUDFLARE_ACCOUNT_ID`.

3. Создай KV-хранилище для списка пользователей и впиши его `id` в `kv_namespaces` в `wrangler.jsonc`:

   ```bash
   npx wrangler kv namespace create ALLOWED_USERS
   ```

4. Задеплой воркер:

   ```bash
   npx wrangler deploy
   ```

5. Задай секреты. `WEBHOOK_SECRET` останется в переменной для следующего шага:

   ```bash
   npx wrangler secret put TELEGRAM_BOT_TOKEN
   npx wrangler secret put ALLOWED_CHAT_ID
   npx wrangler secret put JINA_API_KEY  # необязательно: повышает лимиты Jina

   WEBHOOK_SECRET=$(openssl rand -hex 32)
   printf '%s' "$WEBHOOK_SECRET" | npx wrangler secret put WEBHOOK_SECRET
   ```

6. Зарегистрируй webhook. Без него Telegram не будет отправлять сообщения боту, а без верного секрета воркер отвечает 401:

   ```bash
   read -s "TELEGRAM_BOT_TOKEN?Токен бота: "; echo
   ```

   ```bash
   TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
   WORKER_URL=https://telegram-md-bot.YOUR_SUBDOMAIN.workers.dev \
   WEBHOOK_SECRET="$WEBHOOK_SECRET" \
   npx tsx scripts/set-webhook.mts
   ```

### Обновление работающего бота до версии с `WEBHOOK_SECRET`

Порядок важен: сначала секрет (шаг 5), затем `wrangler deploy` и сразу webhook (шаг 6). Между деплоем и шагом 6 бот отвечает Telegram 401, потом обновления доставятся повторно.

### Использование

| Сообщение | Кто может | Результат |
|-----------|-----------|-----------|
| Текст со ссылкой | Админ и разрешённые пользователи | `.md`-файл со статьёй |
| `/add <id>` | Админ (`ALLOWED_CHAT_ID`) | Разрешить пользователя |
| `/remove <id>` | Админ | Запретить пользователя |
| `/list` | Админ | Список разрешённых |

Остальные пользователи не получают ответа. Сайты за paywall или с жёсткой защитой от ботов вернут ошибку.

---

## Разработка

```bash
uv sync --extra dev

uv run pytest                          # Unit-тесты
uv run pytest tests/contract --no-cov  # Контракт воркеров через wrangler dev, нужен Node.js
uv run ruff check . && uv run ruff format --check .
uvx ty@0.0.99 check src/

cd src/proxyflare/workers/rust && cargo test  # Rust

cd telegram-md-bot && npm ci && npx vitest run  # Бот
```

⚠️ `uv run pytest tests/remote --no-cov` деплоит настоящие воркеры на твой аккаунт Cloudflare и удаляет их после тестов.

| Переменная сборки | Действие |
|-------------------|----------|
| `SKIP_RUST_BUILD=1` | Не собирать Rust-воркер |
| `REQUIRE_RUST_BUILD=1` | Считать неудачную сборку ошибкой, а не предупреждением |

### Бенчмарк

Запусти воркер локально через `wrangler dev`, а затем:

```bash
uv run python scripts/benchmark_worker.py \
  --worker-url http://localhost:8787 \
  --key "$PROXYFLARE_WORKER_KEY" \
  --target-url https://example.com \
  --concurrency 5 \
  --requests 50
```

Ключ можно передать переменной окружения `PROXYFLARE_WORKER_KEY`, чтобы он не попал в историю команд. Бенчмарк создаёт настоящую нагрузку на целевой сайт, так что используй свой сервер.

---

## Структура репозитория

```text
proxyflare_getmd_skill/
├── src/proxyflare/         # CLI и клиентская библиотека (Python)
│   ├── cli/                # Команды: config, create, delete, list, md, test
│   ├── client/             # httpx-транспорт и менеджер воркеров
│   ├── services/           # WorkerService (Cloudflare API)
│   ├── workers/            # Исходники воркеров (js, rust)
│   ├── models/             # Pydantic-модели
│   ├── scripts/            # Сборка Rust-воркера
│   ├── markdown.py         # Скачивание и извлечение статей
│   └── paths.py            # Расположение файлов
├── telegram-md-bot/        # Telegram-бот (TypeScript, Cloudflare Worker)
├── docs/worker-contract.md # Контракт воркеров
├── scripts/                # Бенчмарк
├── tests/
│   ├── unit/               # Без сети
│   ├── contract/           # Воркеры через wrangler dev
│   └── remote/             # Настоящий Cloudflare
└── .env.example            # Шаблон конфигурации
```

---

## Лицензия

MIT
