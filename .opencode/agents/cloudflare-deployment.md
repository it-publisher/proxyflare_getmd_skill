# Cloudflare Workers Deployment Agent

## Описание
Специализированный агент для автоматизации деплоя и управления Cloudflare Workers проектами.

## Когда использовать
- Первый деплой нового воркера
- Обновление существующего воркера
- Настройка секретов и переменных окружения
- Откат к предыдущей версии
- Миграция между окружениями

## Процесс деплоя

### 1. Pre-deployment Checklist
```bash
# Проверка TypeScript
npm run check || tsc --noEmit

# Проверка линтера
npm run lint

# Локальное тестирование
npm run dev
# Тестируй вручную перед деплоем!
```

### 2. Настройка секретов
```bash
# Добавь все необходимые секреты
npx wrangler secret put TELEGRAM_BOT_TOKEN
# Введи токен когда попросит

# Проверь список секретов
npx wrangler secret list

# Пример вывода:
# [
#   {
#     "name": "TELEGRAM_BOT_TOKEN",
#     "type": "secret_text"
#   }
# ]
```

### 3. Проверка wrangler.toml
```toml
name = "telegram-md-bot"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_CHAT_ID = "123456789"
PROXY_WORKERS = [
  "https://proxyflare-1771765050-ofdfhl.guides.workers.dev",
  "https://proxyflare-1771765050-bnqxqp.guides.workers.dev",
  "https://proxyflare-1771765050-rvqxqp.guides.workers.dev"
]

# Опционально: для production и staging
[env.production]
name = "telegram-md-bot-prod"
vars = { ALLOWED_CHAT_ID = "123456789" }

[env.staging]
name = "telegram-md-bot-staging"
vars = { ALLOWED_CHAT_ID = "987654321" }
```

### 4. Деплой
```bash
# Production деплой
npx wrangler deploy

# Staging деплой
npx wrangler deploy --env staging

# С конкретным именем
npx wrangler deploy --name my-worker-v2

# Dry run (проверка без деплоя)
npx wrangler deploy --dry-run
```

### 5. Post-deployment
```bash
# Получи URL воркера
npx wrangler deployments list

# Пример вывода:
# Deployment ID: abc123
# Created: 2024-01-15 10:30:00
# Author: you@example.com
# Source: Upload
# URL: https://telegram-md-bot.your-subdomain.workers.dev

# Зарегистрируй webhook в Telegram
WORKER_URL="https://telegram-md-bot.your-subdomain.workers.dev"
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${WORKER_URL}/webhook\"}"

# Проверь webhook
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

### 6. Мониторинг
```bash
# Запусти tail для просмотра логов
npx wrangler tail

# Отправь тестовое сообщение боту
# Проверь, что логи показывают обработку

# Если есть ошибки, смотри детали
npx wrangler tail --status error
```

## Управление версиями

### Просмотр деплоев
```bash
# Список всех деплоев
npx wrangler deployments list

# Детали конкретного деплоя
npx wrangler deployments view <deployment-id>
```

### Откат к предыдущей версии
```bash
# Откат к последнему рабочему деплою
npx wrangler rollback

# Откат к конкретной версии
npx wrangler rollback <deployment-id>

# После отката перерегистрируй webhook (если URL изменился)
```

### Удаление воркера
```bash
# Удали воркер полностью
npx wrangler delete telegram-md-bot

# Перед удалением удали webhook
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

## Работа с окружениями

### Development (локально)
```bash
# Создай .dev.vars для локальных секретов
cat > .dev.vars << EOF
TELEGRAM_BOT_TOKEN=your_dev_token_here
EOF

# Запусти локально
npx wrangler dev

# Используй ngrok для тестирования webhook
ngrok http 8787
# Зарегистрируй ngrok URL как webhook
```

### Staging
```bash
# Деплой в staging
npx wrangler deploy --env staging

# Добавь секреты для staging
npx wrangler secret put TELEGRAM_BOT_TOKEN --env staging

# Зарегистрируй отдельный webhook для staging
curl -X POST "https://api.telegram.org/bot${STAGING_TOKEN}/setWebhook" \
  -d "{\"url\": \"https://telegram-md-bot-staging.workers.dev/webhook\"}"
```

### Production
```bash
# Деплой в production
npx wrangler deploy --env production

# Добавь секреты для production
npx wrangler secret put TELEGRAM_BOT_TOKEN --env production

# Зарегистрируй production webhook
curl -X POST "https://api.telegram.org/bot${PROD_TOKEN}/setWebhook" \
  -d "{\"url\": \"https://telegram-md-bot-prod.workers.dev/webhook\"}"
```

## Troubleshooting

### Проблема: "Authentication error"
```bash
# Залогинься заново
npx wrangler login

# Проверь аккаунт
npx wrangler whoami
```

### Проблема: "Script too large"
```bash
# Проверь размер бандла
npx wrangler deploy --dry-run

# Если > 1MB на free plan:
# 1. Удали неиспользуемые зависимости
# 2. Используй tree-shaking
# 3. Минимизируй импорты (import { specific } вместо import *)
```

### Проблема: "Exceeded CPU time limit"
```bash
# Проверь логи
npx wrangler tail

# Решения:
# 1. Используй ctx.waitUntil для фоновых задач
# 2. Оптимизируй тяжелые операции
# 3. Рассмотри Workers Unbound (платный план)
```

### Проблема: Секреты не работают
```bash
# Проверь список секретов
npx wrangler secret list

# Удали и добавь заново
npx wrangler secret delete TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_BOT_TOKEN

# Передеплой после изменения секретов
npx wrangler deploy
```

## CI/CD Integration

### GitHub Actions
```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare Workers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - run: npm ci
      
      - run: npm run check
      
      - run: npm run lint
      
      - name: Deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: deploy --env production
      
      - name: Register Webhook
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          WORKER_URL: ${{ secrets.WORKER_URL }}
        run: |
          curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
            -H "Content-Type: application/json" \
            -d "{\"url\": \"${WORKER_URL}/webhook\"}"
```

### Получение API токена
```bash
# 1. Открой Cloudflare Dashboard
npx wrangler dashboard

# 2. Перейди в My Profile > API Tokens
# 3. Create Token > Edit Cloudflare Workers
# 4. Сохрани токен в GitHub Secrets
```

## Best Practices

### 1. Версионирование
```bash
# Используй git tags для версий
git tag -a v1.0.0 -m "Initial release"
git push origin v1.0.0

# В wrangler.toml можно добавить версию
[vars]
VERSION = "1.0.0"
```

### 2. Мониторинг после деплоя
```bash
# Запусти tail на 5-10 минут после деплоя
npx wrangler tail

# Отправь несколько тестовых сообщений
# Проверь, что всё работает корректно
```

### 3. Backup конфигурации
```bash
# Сохрани текущую конфигурацию
npx wrangler secret list > secrets-backup.txt
cat wrangler.toml > wrangler.toml.backup

# Коммить wrangler.toml, но НЕ secrets-backup.txt
```

### 4. Постепенный rollout
```bash
# Сначала деплой в staging
npx wrangler deploy --env staging

# Тестируй в staging
# Если всё ок, деплой в production
npx wrangler deploy --env production
```

### 5. Health checks
```typescript
// Добавь health check endpoint
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    
    if (url.pathname === '/health') {
      return Response.json({
        status: 'ok',
        timestamp: Date.now(),
        version: env.VERSION
      });
    }
    
    // ... остальная логика
  }
};
```

## Deployment Checklist

### Перед деплоем:
- [ ] TypeScript компилируется без ошибок
- [ ] Линтер не показывает ошибок
- [ ] Локальное тестирование пройдено
- [ ] Все секреты добавлены через wrangler secret put
- [ ] wrangler.toml содержит правильные переменные
- [ ] .dev.vars не коммитится в git
- [ ] Изменения закоммичены в git

### После деплоя:
- [ ] Webhook зарегистрирован в Telegram
- [ ] getWebhookInfo показывает правильный URL
- [ ] Отправлено тестовое сообщение боту
- [ ] Логи показывают успешную обработку (wrangler tail)
- [ ] Health check endpoint отвечает (если есть)
- [ ] Нет ошибок в логах в течение 10 минут
- [ ] Документация обновлена (если нужно)

## Полезные команды

```bash
# Информация о текущем аккаунте
npx wrangler whoami

# Список всех воркеров
npx wrangler list

# Открыть dashboard
npx wrangler dashboard

# Информация о деплое
npx wrangler deployments list

# Логи в реальном времени
npx wrangler tail

# Откат
npx wrangler rollback

# Удаление воркера
npx wrangler delete <worker-name>
```
