# Project Rules - Telegram Bot (Cloudflare Workers)

## Общие правила разработки

### Язык и стиль кода
- Используй **TypeScript** для всех файлов воркеров
- Строгая типизация: `strict: true` в tsconfig.json
- Именование: camelCase для переменных/функций, PascalCase для типов/интерфейсов
- Максимальная длина строки: 100 символов
- Используй async/await вместо промисов с .then()

### Структура проекта
```
telegram-md-bot/
├── src/
│   ├── index.ts              # Главный entry point
│   ├── handlers/
│   │   ├── webhook.ts        # Обработка Telegram webhook
│   │   └── telegram.ts       # Telegram API методы
│   ├── services/
│   │   ├── scraper.ts        # Скачивание через прокси
│   │   └── parser.ts         # Readability + Turndown
│   ├── utils/
│   │   ├── validation.ts     # Валидация chat.id, URL
│   │   └── helpers.ts        # Slug, random proxy
│   └── types.ts              # TypeScript типы
├── wrangler.toml
├── package.json
└── tsconfig.json
```

### Безопасность

#### 1. Никогда не коммить секреты
```bash
# ✅ Правильно
npx wrangler secret put TELEGRAM_BOT_TOKEN

# ❌ Неправильно
# wrangler.toml
TELEGRAM_BOT_TOKEN = "123456:ABC..."  # НЕ ДЕЛАЙ ТАК!
```

#### 2. Всегда проверяй chat.id
```typescript
// ✅ Правильно
if (message.chat.id.toString() !== env.ALLOWED_CHAT_ID) {
  return new Response('OK', { status: 200 }); // Игнорируй, но не роняй
}

// ❌ Неправильно
// Обрабатывать все сообщения без проверки
```

#### 3. Валидируй входящие данные
```typescript
// ✅ Правильно
if (!update.message?.text) {
  return new Response('OK', { status: 200 });
}

// ❌ Неправильно
const text = update.message.text; // Может быть undefined
```

### Обработка ошибок

#### 1. Всегда возвращай 200 OK для Telegram
```typescript
// ✅ Правильно
try {
  await processMessage(update, env);
} catch (error) {
  console.error('Error:', error);
  await sendMessage(chatId, 'Произошла ошибка при обработке', env.TELEGRAM_BOT_TOKEN);
}
return new Response('OK', { status: 200 }); // Всегда!

// ❌ Неправильно
return new Response('Error', { status: 500 }); // Telegram будет повторять запрос
```

#### 2. Логируй ошибки подробно
```typescript
// ✅ Правильно
console.error('Failed to fetch URL:', {
  url,
  error: error.message,
  stack: error.stack,
  timestamp: new Date().toISOString()
});

// ❌ Неправильно
console.error(error); // Мало информации
```

#### 3. Информируй пользователя об ошибках
```typescript
// ✅ Правильно
await sendMessage(chatId, '❌ Не удалось скачать страницу. Проверь URL.', token);

// ❌ Неправильно
// Молчаливо игнорировать ошибку
```

### Работа с Telegram API

#### 1. Используй правильные типы
```typescript
interface TelegramUpdate {
  update_id: number;
  message?: {
    message_id: number;
    chat: {
      id: number;
      type: string;
    };
    text?: string;
    from?: {
      id: number;
      username?: string;
    };
  };
}
```

#### 2. Обрабатывай rate limits
```typescript
// Telegram: 30 сообщений/секунду на бота
// Для личного использования это не проблема, но логируй
if (!response.ok) {
  const error = await response.json();
  console.error('Telegram API error:', error);
}
```

#### 3. Используй Markdown для форматирования
```typescript
await sendMessage(
  chatId,
  '✅ Статья обработана!\n\n*Заголовок:* ' + title,
  token,
  'Markdown'
);
```

### Работа с прокси

#### 1. Случайный выбор прокси
```typescript
// ✅ Правильно
function getRandomProxy(proxies: string[]): string {
  return proxies[Math.floor(Math.random() * proxies.length)];
}

// ❌ Неправильно
const proxy = proxies[0]; // Всегда один и тот же
```

#### 2. Retry логика
```typescript
// ✅ Правильно
async function fetchWithRetry(url: string, proxies: string[], maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const proxy = getRandomProxy(proxies);
      return await fetchThroughProxy(url, proxy);
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      console.warn(`Retry ${i + 1}/${maxRetries}`);
    }
  }
}
```

#### 3. Timeout для запросов
```typescript
// ✅ Правильно
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 10000); // 10 сек

try {
  const response = await fetch(url, { signal: controller.signal });
} finally {
  clearTimeout(timeout);
}
```

### Парсинг и конвертация

#### 1. Проверяй результат Readability
```typescript
// ✅ Правильно
const article = reader.parse();
if (!article || !article.content) {
  throw new Error('Failed to extract article content');
}

// ❌ Неправильно
const article = reader.parse();
const markdown = htmlToMarkdown(article.content); // Может быть null
```

#### 2. Очищай Markdown
```typescript
// ✅ Правильно
function cleanMarkdown(md: string): string {
  return md
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+$/gm, '')
    .trim();
}
```

#### 3. Генерируй безопасные имена файлов
```typescript
// ✅ Правильно
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .substring(0, 50) + '.md';
}

// ❌ Неправильно
const filename = title + '.md'; // Может содержать /\:*?"<>|
```

### Производительность

#### 1. Минимизируй CPU time
```typescript
// ✅ Правильно - используй ctx.waitUntil для фоновых задач
ctx.waitUntil(logAnalytics(update));

// ❌ Неправильно - блокирует ответ
await logAnalytics(update);
```

#### 2. Используй streaming для больших файлов
```typescript
// Если статья > 1MB, используй streaming
if (contentLength > 1_000_000) {
  return streamToMarkdown(response);
}
```

#### 3. Кешируй повторяющиеся запросы
```typescript
// Если один URL запрашивается несколько раз
const cache = caches.default;
const cached = await cache.match(url);
if (cached) return cached;
```

### Тестирование

#### 1. Тестируй локально перед деплоем
```bash
# Всегда запускай локально
npx wrangler dev

# Тестируй с реальными URL
curl -X POST http://localhost:8787/webhook \
  -H "Content-Type: application/json" \
  -d '{"message": {"chat": {"id": 123}, "text": "https://example.com"}}'
```

#### 2. Тестируй разные типы сайтов
- Habr (русский контент)
- Medium (английский)
- GitHub README
- Заблокированные сайты (через прокси)

#### 3. Проверяй edge cases
- Невалидные URL
- Сайты без контента
- Очень большие статьи (>10MB)
- Сайты с редиректами

### Git workflow

#### 1. Коммиты
```bash
# ✅ Правильно
git commit -m "feat: add webhook handler for Telegram"
git commit -m "fix: handle missing article content"
git commit -m "refactor: extract parser to separate service"

# ❌ Неправильно
git commit -m "update"
git commit -m "fix bug"
```

#### 2. Не коммить
- `.dev.vars` (локальные секреты)
- `node_modules/`
- `.wrangler/` (build артефакты)
- Любые файлы с токенами

#### 3. Перед коммитом
```bash
# Проверь типы
npm run check

# Запусти линтер
npm run lint

# Протестируй локально
npm run dev
```

### Деплой

#### 1. Checklist перед деплоем
- [ ] TypeScript компилируется без ошибок
- [ ] Все секреты добавлены через `wrangler secret put`
- [ ] Протестировано локально с реальными URL
- [ ] wrangler.toml содержит правильные переменные
- [ ] Webhook зарегистрирован в Telegram

#### 2. Деплой
```bash
# Production деплой
npx wrangler deploy

# Проверь логи после деплоя
npx wrangler tail
```

#### 3. После деплоя
```bash
# Зарегистрируй webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-worker.workers.dev/webhook"}'

# Проверь статус webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### Мониторинг

#### 1. Логируй важные события
```typescript
console.log('Processing URL:', { url, chatId, timestamp: Date.now() });
console.log('Article parsed:', { title, contentLength: content.length });
console.log('File sent:', { filename, size: blob.size });
```

#### 2. Отслеживай ошибки
```typescript
console.error('Scraping failed:', {
  url,
  error: error.message,
  proxy: proxyUsed,
  retries: attemptNumber
});
```

#### 3. Используй wrangler tail
```bash
# Мониторинг в реальном времени
npx wrangler tail

# Только ошибки
npx wrangler tail --status error
```

## Запрещенные практики

### ❌ НЕ ДЕЛАЙ:
1. Не храни токены в коде или wrangler.toml
2. Не обрабатывай сообщения от неавторизованных пользователей
3. Не возвращай 500 ошибки для Telegram webhook
4. Не используй синхронные операции (блокируют event loop)
5. Не игнорируй ошибки молча
6. Не коммить .dev.vars или .env файлы
7. Не деплой без локального тестирования
8. Не используй console.log для секретов
9. Не забывай про rate limits Telegram API
10. Не парси HTML без проверки на null/undefined

## Полезные команды

```bash
# Разработка
npm run dev                    # Локальный сервер
npm run check                  # Проверка типов
npm run lint                   # Линтер

# Деплой
npx wrangler deploy            # Production
npx wrangler tail              # Логи

# Секреты
npx wrangler secret put TOKEN  # Добавить
npx wrangler secret list       # Список

# Telegram
curl "https://api.telegram.org/bot<TOKEN>/getMe"           # Проверка бота
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"  # Статус webhook
```
