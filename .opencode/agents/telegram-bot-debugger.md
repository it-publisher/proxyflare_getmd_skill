# Telegram Bot Debugger Agent

## Описание
Специализированный агент для отладки и диагностики проблем с Telegram-ботом на Cloudflare Workers.

## Когда использовать
- Бот не отвечает на сообщения
- Webhook не работает
- Ошибки при парсинге страниц
- Проблемы с отправкой файлов
- Rate limit или API ошибки

## Диагностические шаги

### 1. Проверка статуса бота
```bash
# Проверь, что бот активен
curl "https://api.telegram.org/bot<TOKEN>/getMe"

# Ожидаемый ответ:
# {"ok":true,"result":{"id":123456,"is_bot":true,"first_name":"MyBot",...}}
```

### 2. Проверка webhook
```bash
# Получи информацию о webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Проверь:
# - url: должен быть твой Workers URL
# - has_custom_certificate: false
# - pending_update_count: должен быть 0 или небольшое число
# - last_error_date: не должно быть (или старая дата)
```

### 3. Проверка логов Workers
```bash
# Запусти tail и отправь сообщение боту
npx wrangler tail

# Смотри на:
# - Приходят ли POST запросы от Telegram
# - Какие ошибки логируются
# - Время выполнения (CPU time)
```

### 4. Тестирование локально
```bash
# Запусти локально
npx wrangler dev

# Отправь тестовый webhook
curl -X POST http://localhost:8787/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 1,
    "message": {
      "message_id": 1,
      "chat": {"id": 123456789, "type": "private"},
      "text": "https://example.com",
      "from": {"id": 123456789, "username": "test"}
    }
  }'
```

## Типичные проблемы и решения

### Проблема: Бот не отвечает

**Диагностика:**
```bash
# 1. Проверь webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# 2. Проверь логи
npx wrangler tail
```

**Возможные причины:**
- Webhook не зарегистрирован → Зарегистрируй через setWebhook
- Неправильный ALLOWED_CHAT_ID → Проверь переменную в wrangler.toml
- Воркер падает с ошибкой → Смотри логи через wrangler tail
- Превышен CPU time limit → Оптимизируй код или используй ctx.waitUntil

**Решение:**
```bash
# Перерегистрируй webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-worker.workers.dev/webhook"}'

# Проверь переменные
npx wrangler tail
# Отправь сообщение и смотри, что логируется
```

### Проблема: "Failed to fetch URL"

**Диагностика:**
```typescript
// Добавь подробное логирование
console.log('Fetching URL:', url);
console.log('Using proxy:', proxy);

try {
  const response = await fetch(proxy, { ... });
  console.log('Response status:', response.status);
  console.log('Response headers:', Object.fromEntries(response.headers));
} catch (error) {
  console.error('Fetch error:', error.message, error.stack);
}
```

**Возможные причины:**
- Прокси не работает → Проверь Proxyflare воркеры
- URL заблокирован → Попробуй другой прокси
- Timeout → Увеличь timeout или добавь retry
- Неправильный формат запроса к прокси → Проверь headers

**Решение:**
```typescript
// Добавь retry с разными прокси
async function fetchWithRetry(url: string, proxies: string[], maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const proxy = proxies[Math.floor(Math.random() * proxies.length)];
    try {
      console.log(`Attempt ${i + 1}: Using proxy ${proxy}`);
      const response = await fetch(proxy, {
        method: 'POST',
        headers: { 'X-Target-URL': url },
        signal: AbortSignal.timeout(10000)
      });
      
      if (response.ok) return response;
      console.warn(`Proxy returned ${response.status}`);
    } catch (error) {
      console.error(`Attempt ${i + 1} failed:`, error.message);
      if (i === maxRetries - 1) throw error;
    }
  }
}
```

### Проблема: "Failed to parse article"

**Диагностика:**
```typescript
// Логируй HTML перед парсингом
console.log('HTML length:', html.length);
console.log('HTML preview:', html.substring(0, 500));

const article = reader.parse();
console.log('Article parsed:', {
  hasTitle: !!article?.title,
  hasContent: !!article?.content,
  contentLength: article?.content?.length
});
```

**Возможные причины:**
- Сайт вернул не HTML (JSON, XML, etc.) → Проверь Content-Type
- Readability не смог найти контент → Попробуй другую стратегию
- HTML слишком большой → Добавь лимит на размер
- Динамический контент (SPA) → Readability не работает с JS

**Решение:**
```typescript
// Fallback стратегии
function parseArticle(html: string, url: string) {
  const dom = new JSDOM(html, { url });
  const reader = new Readability(dom.window.document);
  let article = reader.parse();
  
  // Fallback 1: Ищем <article> тег
  if (!article) {
    const articleTag = dom.window.document.querySelector('article');
    if (articleTag) {
      article = {
        title: dom.window.document.title,
        content: articleTag.innerHTML
      };
    }
  }
  
  // Fallback 2: Ищем main контент
  if (!article) {
    const main = dom.window.document.querySelector('main, [role="main"]');
    if (main) {
      article = {
        title: dom.window.document.title,
        content: main.innerHTML
      };
    }
  }
  
  if (!article) {
    throw new Error('Could not extract article content');
  }
  
  return article;
}
```

### Проблема: "Failed to send document"

**Диагностика:**
```typescript
// Логируй перед отправкой
console.log('Sending document:', {
  filename,
  size: blob.size,
  type: blob.type,
  chatId
});

const response = await fetch(url, { method: 'POST', body: formData });
console.log('Telegram response:', response.status);

if (!response.ok) {
  const error = await response.json();
  console.error('Telegram error:', error);
}
```

**Возможные причины:**
- Файл слишком большой (>50MB) → Telegram лимит
- Неправильный формат FormData → Проверь append
- Неправильный токен → Проверь TELEGRAM_BOT_TOKEN
- Rate limit → Слишком много запросов

**Решение:**
```typescript
// Проверь размер перед отправкой
if (blob.size > 50 * 1024 * 1024) {
  await sendMessage(
    chatId,
    '❌ Файл слишком большой (>50MB). Попробуй другую статью.',
    token
  );
  return;
}

// Правильный FormData
const formData = new FormData();
formData.append('chat_id', chatId.toString());
formData.append('document', blob, filename);
formData.append('caption', `📄 ${title}`);

// Отправка с обработкой ошибок
const response = await fetch(
  `https://api.telegram.org/bot${token}/sendDocument`,
  { method: 'POST', body: formData }
);

if (!response.ok) {
  const error = await response.json();
  console.error('Telegram API error:', error);
  throw new Error(`Telegram API: ${error.description}`);
}
```

### Проблема: "CPU time limit exceeded"

**Диагностика:**
```typescript
// Измеряй время выполнения
const start = Date.now();

// ... твой код ...

const duration = Date.now() - start;
console.log('Execution time:', duration, 'ms');
```

**Возможные причины:**
- Парсинг большого HTML → Оптимизируй или используй streaming
- Синхронные операции → Используй async/await
- Тяжелые регулярные выражения → Упрости
- Много итераций → Оптимизируй алгоритмы

**Решение:**
```typescript
// Используй ctx.waitUntil для неблокирующих операций
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const update = await request.json();
    
    // Быстрый ответ Telegram
    ctx.waitUntil(
      processMessage(update, env).catch(error => {
        console.error('Background processing failed:', error);
      })
    );
    
    return new Response('OK', { status: 200 });
  }
};

// Или используй Workers Unbound (платный план)
// compatibility_flags = ["nodejs_compat"]
```

## Debugging Checklist

### Перед обращением за помощью, проверь:
- [ ] Бот активен (getMe возвращает ok: true)
- [ ] Webhook зарегистрирован (getWebhookInfo показывает правильный URL)
- [ ] ALLOWED_CHAT_ID совпадает с твоим chat.id
- [ ] TELEGRAM_BOT_TOKEN добавлен через wrangler secret put
- [ ] Proxyflare воркеры работают (проверь вручную)
- [ ] Логи показывают входящие запросы (wrangler tail)
- [ ] Нет ошибок TypeScript (npm run check)
- [ ] Локальное тестирование работает (wrangler dev)
- [ ] Воркер задеплоен (wrangler deploy)
- [ ] Нет превышения CPU time (смотри логи)

## Полезные команды для отладки

```bash
# Проверка бота
curl "https://api.telegram.org/bot<TOKEN>/getMe"

# Проверка webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Удаление webhook (для тестирования)
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Получение обновлений вручную (без webhook)
curl "https://api.telegram.org/bot<TOKEN>/getUpdates"

# Отправка тестового сообщения
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": 123456789, "text": "Test"}'

# Логи Workers
npx wrangler tail

# Логи с фильтром
npx wrangler tail --status error

# Информация о деплое
npx wrangler deployments list

# Откат к предыдущей версии
npx wrangler rollback
```

## Мониторинг в production

### Добавь структурированное логирование
```typescript
function log(level: string, message: string, data?: any) {
  console.log(JSON.stringify({
    level,
    message,
    data,
    timestamp: new Date().toISOString()
  }));
}

// Использование
log('info', 'Processing URL', { url, chatId });
log('error', 'Failed to fetch', { url, error: error.message });
```

### Отслеживай метрики
```typescript
// В конце обработки
log('metrics', 'Request completed', {
  duration: Date.now() - startTime,
  success: true,
  url,
  articleLength: markdown.length
});
```

### Алерты при ошибках
```typescript
// Если критическая ошибка, отправь себе уведомление
if (criticalError) {
  await sendMessage(
    env.ADMIN_CHAT_ID,
    `🚨 Critical error: ${error.message}`,
    env.TELEGRAM_BOT_TOKEN
  );
}
```
