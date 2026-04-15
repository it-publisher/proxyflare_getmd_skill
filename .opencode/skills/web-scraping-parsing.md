# Web Scraping & Parsing Skill

## Описание
Специализированные инструкции для парсинга веб-страниц и конвертации HTML в Markdown с использованием @mozilla/readability и turndown.

## Когда использовать
- Извлечение основного контента из веб-страниц
- Конвертация HTML в чистый Markdown
- Работа с различными структурами сайтов
- Обход блокировок через прокси

## Технологический стек
- **@mozilla/readability** - извлечение основного контента
- **turndown** - конвертация HTML → Markdown
- **jsdom** - DOM для Node.js/Workers окружения
- **linkedom** - альтернатива jsdom (легче для Workers)

## Архитектурные принципы

### 1. Fetch через прокси
```typescript
async function fetchThroughProxy(url: string, proxyUrl: string): Promise<string> {
  const response = await fetch(proxyUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Target-URL': url
    }
  });
  
  if (!response.ok) {
    throw new Error(`Failed to fetch: ${response.status}`);
  }
  
  return await response.text();
}
```

### 2. Парсинг с Readability
```typescript
import { Readability } from '@mozilla/readability';
import { JSDOM } from 'jsdom';

function parseArticle(html: string, url: string) {
  const dom = new JSDOM(html, { url });
  const reader = new Readability(dom.window.document);
  const article = reader.parse();
  
  if (!article) {
    throw new Error('Failed to parse article');
  }
  
  return {
    title: article.title,
    content: article.content, // HTML
    textContent: article.textContent,
    excerpt: article.excerpt,
    byline: article.byline,
    siteName: article.siteName
  };
}
```

### 3. Конвертация в Markdown
```typescript
import TurndownService from 'turndown';

function htmlToMarkdown(html: string): string {
  const turndown = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-'
  });
  
  // Кастомные правила для лучшего форматирования
  turndown.addRule('strikethrough', {
    filter: ['del', 's', 'strike'],
    replacement: (content) => `~~${content}~~`
  });
  
  return turndown.turndown(html);
}
```

## Best Practices

### Обработка различных типов контента

#### Статьи с кодом
```typescript
turndown.addRule('codeBlock', {
  filter: (node) => {
    return node.nodeName === 'PRE' && 
           node.firstChild?.nodeName === 'CODE';
  },
  replacement: (content, node) => {
    const code = node.firstChild;
    const language = code.className.replace('language-', '') || '';
    return `\n\`\`\`${language}\n${content}\n\`\`\`\n`;
  }
});
```

#### Изображения
```typescript
turndown.addRule('images', {
  filter: 'img',
  replacement: (content, node) => {
    const alt = node.getAttribute('alt') || '';
    const src = node.getAttribute('src') || '';
    const title = node.getAttribute('title') || '';
    
    return title 
      ? `![${alt}](${src} "${title}")`
      : `![${alt}](${src})`;
  }
});
```

### Очистка и нормализация

#### Удаление лишних пробелов
```typescript
function cleanMarkdown(markdown: string): string {
  return markdown
    .replace(/\n{3,}/g, '\n\n') // Максимум 2 переноса подряд
    .replace(/[ \t]+$/gm, '')    // Пробелы в конце строк
    .trim();
}
```

#### Генерация метаданных
```typescript
function generateFrontmatter(article: Article, url: string): string {
  return `---
title: ${article.title}
source: ${url}
author: ${article.byline || 'Unknown'}
date: ${new Date().toISOString()}
---

`;
}
```

## Работа с проблемными сайтами

### Сайты с динамическим контентом
Readability работает только с уже отрендеренным HTML. Для SPA может потребоваться:
- Использовать Browser Rendering API от Cloudflare
- Искать альтернативные источники (RSS, API)

### Сайты с защитой от скрейпинга
```typescript
const headers = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  'Accept': 'text/html,application/xhtml+xml',
  'Accept-Language': 'en-US,en;q=0.9',
  'Referer': 'https://www.google.com/'
};
```

### Обработка редиректов
```typescript
async function fetchWithRedirects(url: string, maxRedirects = 5): Promise<Response> {
  let response = await fetch(url, { redirect: 'follow' });
  
  if (response.redirected) {
    console.log(`Redirected to: ${response.url}`);
  }
  
  return response;
}
```

## Оптимизация для Cloudflare Workers

### Использование linkedom вместо jsdom
```typescript
// linkedom легче и быстрее для Workers
import { parseHTML } from 'linkedom';

function parseArticle(html: string, url: string) {
  const { document } = parseHTML(html);
  const reader = new Readability(document);
  return reader.parse();
}
```

### Streaming для больших файлов
```typescript
async function streamToMarkdown(response: Response): Promise<string> {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let html = '';
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    html += decoder.decode(value, { stream: true });
  }
  
  return parseAndConvert(html);
}
```

## Типичные проблемы и решения

### Проблема: Readability не находит контент
**Решение:** Попробуй разные стратегии:
```typescript
function tryParse(html: string, url: string) {
  // Стратегия 1: Стандартный Readability
  let article = new Readability(doc).parse();
  
  if (!article) {
    // Стратегия 2: Ищем <article> теги
    const articleTag = doc.querySelector('article');
    if (articleTag) {
      return { content: articleTag.innerHTML };
    }
  }
  
  if (!article) {
    // Стратегия 3: Основной контент по селекторам
    const main = doc.querySelector('main, [role="main"], .content');
    if (main) {
      return { content: main.innerHTML };
    }
  }
  
  return article;
}
```

### Проблема: Плохое форматирование таблиц
**Решение:** Добавь кастомное правило для таблиц:
```typescript
turndown.addRule('tables', {
  filter: 'table',
  replacement: (content, node) => {
    // Конвертируй в GitHub-flavored Markdown таблицы
    return convertTableToMarkdown(node);
  }
});
```

### Проблема: Потеря структуры при конвертации
**Решение:** Сохраняй заголовки и списки:
```typescript
const turndown = new TurndownService({
  headingStyle: 'atx',        // # заголовки
  bulletListMarker: '-',       // - списки
  codeBlockStyle: 'fenced',    // ``` код
  emDelimiter: '*',            // *курсив*
  strongDelimiter: '**'        // **жирный**
});
```

## Тестирование

### Тестовые URL для проверки
```typescript
const testUrls = [
  'https://habr.com/ru/articles/...',      // Русский контент
  'https://medium.com/@user/article',      // Medium
  'https://dev.to/user/article',           // Dev.to
  'https://github.com/user/repo',          // GitHub README
];
```

### Проверка качества парсинга
```typescript
function validateParsing(article: Article): boolean {
  return (
    article.title.length > 0 &&
    article.content.length > 100 &&
    !article.content.includes('cookie') && // Нет cookie баннеров
    !article.content.includes('subscribe') // Нет форм подписки
  );
}
```

## Чеклист
- [ ] Readability корректно извлекает заголовок
- [ ] Сохраняется структура (заголовки, списки, код)
- [ ] Изображения конвертируются с alt-текстом
- [ ] Удаляются навигация, футеры, сайдбары
- [ ] Markdown валидный и читаемый
- [ ] Обрабатываются ошибки (404, timeout, блокировки)

## Полезные ссылки
- [Readability.js](https://github.com/mozilla/readability)
- [Turndown](https://github.com/mixmark-io/turndown)
- [linkedom](https://github.com/WebReflection/linkedom)
