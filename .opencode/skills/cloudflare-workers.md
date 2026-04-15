# Cloudflare Workers Development Skill

## Описание
Специализированные инструкции для разработки на Cloudflare Workers с TypeScript, включая работу с Wrangler CLI, секретами и деплоем.

## Когда использовать
- Разработка serverless функций на Cloudflare Workers
- Настройка и деплой через Wrangler
- Работа с Workers KV, Durable Objects, R2
- Интеграция с Cloudflare Workers AI

## Технологический стек
- **Runtime:** Cloudflare Workers (V8 isolates)
- **Язык:** TypeScript/JavaScript
- **CLI:** Wrangler
- **Стандарты:** Web Standards API (fetch, Request, Response)

## Инициализация проекта

### Создание нового проекта
```bash
npm create cloudflare@latest my-worker
# Выбрать: "Hello World" Worker
# TypeScript: Yes
```

### Структура проекта
```
my-worker/
├── src/
│   └── index.ts          # Основной код воркера
├── wrangler.toml         # Конфигурация
├── package.json
└── tsconfig.json
```

## Конфигурация (wrangler.toml)

### Базовая конфигурация
```toml
name = "telegram-md-bot"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_CHAT_ID = "123456789"
PROXY_WORKERS = ["https://proxy1.workers.dev", "https://proxy2.workers.dev"]

# Секреты добавляются через CLI:
# npx wrangler secret put TELEGRAM_BOT_TOKEN
```

### Переменные окружения
```typescript
interface Env {
  TELEGRAM_BOT_TOKEN: string;      // Секрет
  ALLOWED_CHAT_ID: string;         // Публичная переменная
  PROXY_WORKERS: string[];         // Массив
}
```

## Основные паттерны

### Базовый Worker
```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      // Роутинг
      const url = new URL(request.url);
      
      if (url.pathname === '/webhook' && request.method === 'POST') {
        return await handleWebhook(request, env);
      }
      
      return new Response('Not Found', { status: 404 });
    } catch (error) {
      console.error('Error:', error);
      return new Response('Internal Server Error', { status: 500 });
    }
  }
};
```

### Работа с секретами
```bash
# Добавить секрет
npx wrangler secret put TELEGRAM_BOT_TOKEN

# Список секретов
npx wrangler secret list

# Удалить секрет
npx wrangler secret delete TELEGRAM_BOT_TOKEN
```

### Доступ к секретам в коде
```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token = env.TELEGRAM_BOT_TOKEN; // Безопасно
    // НЕ логируй секреты!
    console.log('Token length:', token.length);
    
    return new Response('OK');
  }
};
```

## Работа с Request/Response

### Парсинг JSON
```typescript
const data = await request.json();
```

### Отправка JSON
```typescript
return new Response(JSON.stringify({ status: 'ok' }), {
  headers: { 'Content-Type': 'application/json' }
});
```

### Работа с FormData
```typescript
const formData = new FormData();
formData.append('file', blob, 'document.md');

await fetch(url, {
  method: 'POST',
  body: formData
});
```

### Проксирование запросов
```typescript
async function proxyRequest(targetUrl: string): Promise<Response> {
  const response = await fetch(targetUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0...',
      'Accept': 'text/html'
    }
  });
  
  return new Response(response.body, {
    status: response.status,
    headers: response.headers
  });
}
```

## Лимиты и ограничения

### Free Plan
- **Requests:** 100,000/день
- **CPU Time:** 10ms/запрос
- **Memory:** 128MB
- **Script Size:** 1MB после сжатия

### Paid Plan ($5/месяц)
- **Requests:** 10,000,000/месяц
- **CPU Time:** 50ms/запрос
- **Memory:** 128MB
- **Script Size:** 10MB

### Обход лимитов CPU Time
```typescript
// Используй ctx.waitUntil для фоновых задач
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Быстрый ответ пользователю
    const response = new Response('Processing...');
    
    // Долгая задача в фоне (не блокирует ответ)
    ctx.waitUntil(
      processLongTask(request, env)
    );
    
    return response;
  }
};
```

## Локальная разработка

### Запуск dev-сервера
```bash
npx wrangler dev
# Доступен на http://localhost:8787
```

### Тестирование с локальными секретами
```bash
# Создай .dev.vars для локальной разработки
echo "TELEGRAM_BOT_TOKEN=your_token_here" > .dev.vars

# .dev.vars НЕ коммитится в git!
```

### Hot reload
Wrangler автоматически перезагружает воркер при изменении файлов.

## Деплой

### Деплой в production
```bash
npx wrangler deploy
```

### Деплой с именем
```bash
npx wrangler deploy --name my-worker-prod
```

### Просмотр деплоев
```bash
npx wrangler deployments list
```

### Откат к предыдущей версии
```bash
npx wrangler rollback
```

## Мониторинг и отладка

### Просмотр логов в реальном времени
```bash
npx wrangler tail
```

### Фильтрация логов
```bash
npx wrangler tail --status error
npx wrangler tail --method POST
```

### Логирование в коде
```typescript
console.log('Info message');
console.error('Error message');
console.warn('Warning message');

// Структурированные логи
console.log(JSON.stringify({
  level: 'info',
  message: 'Request processed',
  duration: 123,
  timestamp: Date.now()
}));
```

## Workers AI Integration

### Настройка AI биндинга
```toml
[ai]
binding = "AI"
```

### Использование AI
```typescript
interface Env {
  AI: any;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await env.AI.run('@cf/meta/llama-3-8b-instruct', {
      messages: [
        { role: 'user', content: 'Summarize this article: ...' }
      ]
    });
    
    return Response.json(response);
  }
};
```

### Доступные модели
- `@cf/meta/llama-3-8b-instruct` - Llama 3
- `@cf/mistral/mistral-7b-instruct` - Mistral
- `@cf/meta/m2m100-1.2b` - Перевод

## Best Practices

### 1. Всегда возвращай Response
```typescript
// ✅ Правильно
return new Response('OK');

// ❌ Неправильно
return 'OK'; // Ошибка типа
```

### 2. Обрабатывай ошибки
```typescript
try {
  await riskyOperation();
} catch (error) {
  console.error('Error:', error);
  return new Response('Error', { status: 500 });
}
```

### 3. Используй TypeScript
```typescript
interface Env {
  TOKEN: string;
}

// Типизация помогает избежать ошибок
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token: string = env.TOKEN;
    return new Response('OK');
  }
};
```

### 4. Оптимизируй размер бандла
```typescript
// ✅ Импортируй только нужное
import { parse } from 'library/parse';

// ❌ Не импортируй всё
import * as library from 'library';
```

### 5. Кешируй запросы
```typescript
const cache = caches.default;

async function fetchWithCache(url: string): Promise<Response> {
  let response = await cache.match(url);
  
  if (!response) {
    response = await fetch(url);
    await cache.put(url, response.clone());
  }
  
  return response;
}
```

## Troubleshooting

### Проблема: "Script exceeded CPU time limit"
**Решение:**
- Используй `ctx.waitUntil()` для фоновых задач
- Оптимизируй тяжелые операции
- Рассмотри Workers Unbound ($0.15/million requests, 400ms CPU)

### Проблема: "Module not found"
**Решение:**
```bash
npm install
npx wrangler deploy
```

### Проблема: Секреты не работают локально
**Решение:**
Создай `.dev.vars`:
```
TELEGRAM_BOT_TOKEN=your_token
```

### Проблема: CORS ошибки
**Решение:**
```typescript
return new Response(body, {
  headers: {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  }
});
```

## Чеклист перед деплоем
- [ ] Все зависимости установлены (`npm install`)
- [ ] TypeScript компилируется без ошибок
- [ ] Секреты добавлены через `wrangler secret put`
- [ ] wrangler.toml настроен корректно
- [ ] Протестировано локально (`wrangler dev`)
- [ ] .dev.vars не коммитится в git
- [ ] Логирование настроено для отладки
- [ ] Обработка ошибок реализована

## Полезные команды
```bash
# Информация о воркере
npx wrangler whoami

# Список воркеров
npx wrangler list

# Удалить воркер
npx wrangler delete my-worker

# Открыть dashboard
npx wrangler dashboard
```

## Полезные ссылки
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)
- [Workers Examples](https://developers.cloudflare.com/workers/examples/)
- [Workers AI](https://developers.cloudflare.com/workers-ai/)
