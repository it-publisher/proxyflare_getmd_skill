# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.27",
#   "trafilatura>=2.0",
#   # Клиент берётся с PyPI, а не из этого репозитория, поэтому версия зафиксирована
#   "proxyflare==0.1.2",
# ]
# ///

"""
Утилита для скачивания веб-страниц и конвертации их в формат Markdown.

В скрипте реализован подход "Единой ответственности" (Single Responsibility Principle):
каждая функция отвечает ровно за одну задачу (скачивание, парсинг, сохранение).
Это делает код читаемым, легко тестируемым и поддерживаемым.

Основные улучшения:
1. Использование argparse для удобного запуска из командной строки с параметрами.
2. Аннотации типов для статической проверки и автокомплита в IDE.
3. Пути по умолчанию считаются от папки скрипта, поэтому он работает из любой директории.
4. Разделение логики на четкие этапы (Fetch -> Extract -> Save).
"""

import argparse
import json
import re
import secrets
import sys
from datetime import date, datetime
from pathlib import Path

import httpx
import trafilatura

from proxyflare.client.manager import ProxyflareWorkersManager
from proxyflare.client.transport import ProxyflareTransport

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROXY_CONFIG = SCRIPT_DIR / "proxyflare-workers.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "articles"

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 25.0
# Лимит имени файла в ФС — 255 байт. Запас нужен под суффикс времени и расширение
MAX_SLUG_BYTES = 200

# Имитация реального браузера, чтобы снизить риск блокировки
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def print_error(message: str) -> None:
    """Печатает сообщение об ошибке в stderr, чтобы stdout оставался чистым."""
    print(message, file=sys.stderr)


def slugify(text: str) -> str:
    """
    Превращает произвольный текст в безопасное имя файла (slug).

    Убирает все специальные символы, оставляет только буквы, цифры и дефисы.
    Пробелы и знаки подчеркивания заменяются на дефис.

    Args:
        text: Исходная строка (например, заголовок статьи).
    Returns:
        Непустая строка, пригодная для использования в качестве имени файла.
    """
    text = text.lower()
    # Оставляем только буквы, цифры и дефисы
    text = re.sub(r"[^\w\s-]", "", text)
    # Заменяем пробелы и подчеркивания на одиночные дефисы
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    # Режем по байтам, а не по символам: кириллица занимает 2 байта на символ
    text = text.encode()[:MAX_SLUG_BYTES].decode(errors="ignore").rstrip("-")
    return text or "article"


def request_page(url: str, worker_url: str) -> httpx.Response:
    """Выполняет один запрос к странице через указанный воркер."""
    manager = ProxyflareWorkersManager(source=[worker_url])
    with httpx.Client(
        transport=ProxyflareTransport(manager),
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=BROWSER_HEADERS,
    ) as client:
        return client.get(url)


def is_worker_failure(response: httpx.Response) -> bool:
    """Решает, есть ли смысл повторить запрос через другой воркер."""
    if response.status_code == 429 or response.status_code >= 500:
        return True
    # Воркеры добавляют этот заголовок к ответам сайта. Без него ответ дал сам Cloudflare,
    # например 404 удалённого воркера, и это ничего не говорит о целевом сайте.
    return "access-control-allow-origin" not in response.headers


def decode_body(response: httpx.Response) -> str | bytes:
    """Возвращает тело ответа в виде, подходящем для разбора HTML."""
    # Без charset в заголовке httpx декодирует как UTF-8 и портит, например, windows-1251.
    # Байты позволяют trafilatura определить кодировку самой.
    return response.text if response.charset_encoding else response.content


def fetch_html(url: str, proxy_config: str | Path) -> str | bytes | None:
    """
    Загружает HTML страницы, используя Proxyflare для обхода блокировок.

    Если воркер не отвечает, повторяет запрос через другой. Ошибка самого сайта,
    например 403 или 404, повтором не исправится, поэтому возвращается сразу.

    Args:
        url: Ссылка на страницу для скачивания.
        proxy_config: Путь к JSON конфигурации воркеров Proxyflare.

    Returns:
        HTML страницы, или None в случае ошибки.
    """
    try:
        workers = ProxyflareWorkersManager(source=proxy_config).workers
    except (ValueError, OSError) as e:
        print_error(f"❌ Ошибка настройки воркеров: {e}")
        return None

    attempts = secrets.SystemRandom().sample(workers, k=min(MAX_ATTEMPTS, len(workers)))

    print(f"🕵️  Запрос через Cloudflare: {url}")
    for number, worker_url in enumerate(attempts, start=1):
        try:
            response = request_page(url, worker_url)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            print_error(f"⚠️  Попытка {number}/{len(attempts)}: {e or type(e).__name__}")
            continue

        if is_worker_failure(response):
            print_error(f"⚠️  Попытка {number}/{len(attempts)}: HTTP {response.status_code}")
            continue

        if not response.is_success:
            print_error(f"❌ Сайт ответил HTTP {response.status_code}")
            return None

        return decode_body(response)

    print_error("❌ Не удалось скачать страницу: все попытки исчерпаны.")
    return None


def extract_content(html: str | bytes) -> tuple[str, str | None]:
    """
    Извлекает полезную информацию (заголовок и основной контент) из "сырого" HTML.
    Использует библиотеку trafilatura для умной очистки текста от рекламы и меню.

    Args:
        html: Исходный код страницы.

    Returns:
        Кортеж (Заголовок статьи, Markdown контент).
    """
    # Попытка извлечь структурированные метаданные (например, тег <title>)
    metadata = trafilatura.metadata.extract_metadata(html)

    # Резервный вариант: если заголовка нет, используем текущую дату и время
    title = (
        metadata.title
        if metadata and metadata.title
        else f"article_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Непосредственное извлечение контента с конвертацией в Markdown
    content = trafilatura.extract(
        html, include_comments=False, include_tables=True, output_format="markdown"
    )
    return title, content


def format_document(title: str, url: str, content: str) -> str:
    """Собирает итоговый Markdown: метаданные, заголовок и текст статьи."""
    single_line_title = " ".join(title.split())
    # Текст часто начинается с H1 самой страницы, и второй заголовок стал бы дублем
    heading = "" if content.lstrip().startswith("# ") else f"# {single_line_title}\n\n"
    # JSON-строка — это валидная строка YAML, так что кавычки и двоеточия в заголовке безопасны
    return (
        "---\n"
        f"title: {json.dumps(single_line_title, ensure_ascii=False)}\n"
        f"source: {json.dumps(url, ensure_ascii=False)}\n"
        f"saved: {date.today().isoformat()}\n"
        "---\n\n"
        f"{heading}{content}\n"
    )


def save_markdown(title: str, document: str, output_dir: Path) -> Path | None:
    """
    Отвечает только за работу с файловой системой.
    Сохраняет документ в markdown файл с уникальным именем.

    Args:
        title: Заголовок для формирования имени файла.
        document: Текст в формате Markdown.
        output_dir: Папка для сохранения (будет создана, если не существует).

    Returns:
        Путь к сохраненному файлу, или None в случае ошибки ввода-вывода.
    """
    file_path = output_dir / f"{slugify(title)}.md"

    # Защита от потери данных: добавляем timestamp, если файл уже существует
    if file_path.exists():
        timestamp = datetime.now().strftime("%H%M%S")
        file_path = output_dir / f"{slugify(title)}_{timestamp}.md"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(document, encoding="utf-8")
        return file_path
    except OSError as e:
        print_error(f"❌ Ошибка при сохранении файла: {e}")
        return None


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Скачивает статью из веба и чисто сохраняет её в формате Markdown."
    )
    parser.add_argument("url", help="URL статьи для скачивания")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Папка для сохранения (по умолчанию: articles рядом со скриптом)",
    )
    parser.add_argument(
        "-p",
        "--proxy-config",
        type=Path,
        default=DEFAULT_PROXY_CONFIG,
        help="Путь к конфигу Proxyflare (по умолчанию: proxyflare-workers.json рядом со скриптом)",
    )
    return parser.parse_args()


def main() -> int:
    """
    Главная точка входа: оркестрация вызовов (Fetch -> Extract -> Save).

    Returns:
        Код возврата процесса: 0 при успехе, 1 при любой ошибке.
    """
    args = parse_args()

    # Шаг 1. Получение данных (сеть)
    html = fetch_html(args.url, args.proxy_config)
    if html is None:
        return 1

    # Шаг 2. Парсинг данных (очистка и форматирование)
    title, content = extract_content(html)
    if not content:
        print_error("⚠️  Контент не найден или статья слишком мала.")
        return 1

    # Шаг 3. Сохранение (файловая система)
    document = format_document(title, args.url, content)
    saved_path = save_markdown(title, document, args.output)
    if saved_path is None:
        return 1

    print(f"✅ Успешно! Файл сохранен: {saved_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
