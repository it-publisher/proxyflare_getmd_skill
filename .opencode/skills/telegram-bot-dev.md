# Telegram Bot Development Skill

## Описание
Специализированные инструкции для разработки Telegram-ботов на Cloudflare Workers с использованием TypeScript.

## Когда использовать
- Разработка webhook-обработчиков для Telegram Bot API
- Интеграция с Telegram API (sendMessage, sendDocument, etc.)
- Работа с Telegram типами и структурами данных

## Технологический стек
- **Runtime:** Cloudflare Workers
- **Язык:** TypeScript
- **API:** Telegram Bot API
- **Инструменты:** Wrangler CLI

## Архитектурные принципы

### 1. Webhook Handler Pattern
```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }
    
    const update = await request.json();
    await handleUpdate(update, env);
    
    // Всегда возвращать 200 OK для Telegram
    return new Response('OK', { status: 200 });
  }
}
```

### 2. Security First
- **Всегда проверяй chat.id** перед обработкой команд
- Используй секреты через `env` (не хардкодь токены)
- Валидируй входящие данные от Telegram
- Игнорируй неавторизованные запросы (но возвращай 200 OK)

### 3. Error Handling
- Оборачивай всю логику в try-catch
- При ошибках отправляй пользователю понятное сообщение
- Логируй ошибки через console.error (видны в wrangler tail)
- Никогда не роняй воркер (всегда возвращай 200 OK)

## Telegram Bot API Best Practices

### Отправка сообщений
```typescript
async function sendMessage(chatId: number, text: string, token: string) {
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: 'Markdown' // или 'HTML'
    })
  });
}
```

### Отправка файлов (sendDocument)
```typescript
async function sendDocument(chatId: number, file: Blob, filename: string, token: string) {
  const formData = new FormData();
  formData.append('chat_id', chatId.toString());
  formData.append('document', file, filename);
  
  const url = `https://api.telegram.org/bot${token}/sendDocument`;
  await fetch(url, {
    method: 'POST',
    body: formData
  });
}
```

### Регистрация Webhook
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-worker.workers.dev"}'
```

## Cloudflare Workers Специфика

### Секреты и переменные окружения
```toml
# wrangler.toml
[vars]
ALLOWED_CHAT_ID = "123456789"

# Секреты добавляются через CLI:
# npx wrangler secret put TELEGRAM_BOT_TOKEN
```

### Лимиты и ограничения
- **CPU Time:** 50ms на бесплатном плане (обычно достаточно)
- **Memory:** 128MB
- **Request Size:** 100MB
- **Response Size:** Без лимита для streaming

### Работа с FormData
В Workers FormData работает нативно, но для создания Blob из строки:
```typescript
const blob = new Blob([markdownContent], { type: 'text/markdown' });
```

## Типичные паттерны

### Извлечение URL из сообщения
```typescript
function extractUrl(text: string): string | null {
  const urlRegex = /(https?:\/\/[^\s]+)/;
  const match = text.match(urlRegex);
  return match ? match[1] : null;
}
```

### Случайный выбор прокси
```typescript
function getRandomProxy(proxies: string[]): string {
  return proxies[Math.floor(Math.random() * proxies.length)];
}
```

### Генерация slug для имени файла
```typescript
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .substring(0, 50);
}
```

## Debugging

### Локальная разработка
```bash
npx wrangler dev
```

### Просмотр логов в реальном времени
```bash
npx wrangler tail
```

### Тестирование webhook локально
Используй ngrok или cloudflared tunnel для проброса локального порта.

## Чеклист перед деплоем
- [ ] Все секреты добавлены через `wrangler secret put`
- [ ] ALLOWED_CHAT_ID прописан в wrangler.toml
- [ ] Webhook зарегистрирован в Telegram
- [ ] Протестирована обработка ошибок
- [ ] Проверена работа с разными типами URL
- [ ] Логирование настроено для отладки

## Полезные ссылки
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)
