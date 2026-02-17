#!/usr/bin/env python3
"""Получение актуальной цены товара Ozon с учётом авторизации.

Сценарий поддерживает два режима:
1) Одноразовое сохранение авторизованной сессии (storage_state.json).
2) Регулярный запуск на VPS с уже сохранённой сессией.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Error, TimeoutError, sync_playwright


PRICE_SELECTORS = [
    "[data-widget='webPrice']",
    "[data-widget='webCurrentPrice']",
    "[data-widget='price']",
    "[data-widget='pdpPrice']",
    "[data-widget='webSale']",
    "span.tsHeadline500Medium",
    "div[data-widget='webPrice'] span",
]


@dataclass
class PriceResult:
    product_url: str
    price_raw: str
    price_value: int
    currency: str = "RUB"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Собирает цену карточки товара Ozon с авторизованной сессией."
    )
    parser.add_argument("url", help="Ссылка на карточку товара ozon.ru")
    parser.add_argument(
        "--storage-state",
        default="ozon_storage_state.json",
        help="Путь к файлу Playwright storage_state JSON",
    )
    parser.add_argument(
        "--browser",
        choices=["chromium", "firefox", "webkit"],
        default="chromium",
        help="Движок браузера Playwright",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Таймаут ожидания страницы/селекторов в мс",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Запускать браузер с UI (для первичной авторизации)",
    )
    parser.add_argument(
        "--save-storage-state",
        action="store_true",
        help="Открыть Ozon и сохранить авторизованную сессию в --storage-state",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Печатать результат в JSON",
    )
    return parser.parse_args()


def create_context(playwright, browser_name: str, headful: bool, storage_state: Optional[Path]) -> BrowserContext:
    browser_type = getattr(playwright, browser_name)
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
    ]
    browser = browser_type.launch(headless=not headful, args=launch_args)

    context_kwargs = {
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1366, "height": 900},
    }

    if storage_state and storage_state.exists():
        context_kwargs["storage_state"] = str(storage_state)

    return browser.new_context(**context_kwargs)


def ensure_logged_in_state(context: BrowserContext, storage_state_path: Path, timeout_ms: int) -> None:
    page = context.new_page()
    page.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=timeout_ms)
    print(
        "[INFO] Войдите в аккаунт в открытом браузере. "
        "После успешного входа нажмите Enter в консоли...",
        file=sys.stderr,
    )
    input()
    context.storage_state(path=str(storage_state_path))
    print(f"[INFO] Сессия сохранена: {storage_state_path}", file=sys.stderr)
    page.close()


def extract_price_from_text(text: str) -> Optional[int]:
    cleaned = text.replace("\u2009", " ").replace("\xa0", " ")
    match = re.search(r"(\d[\d\s]{1,15})\s*[₽рRUB]", cleaned, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"(\d[\d\s]{1,15})", cleaned)
    if not match:
        return None

    digits = re.sub(r"\D", "", match.group(1))
    if not digits:
        return None
    return int(digits)


def extract_price(page, timeout_ms: int) -> PriceResult:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(2500)

    for selector in PRICE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=3000).strip()
            price = extract_price_from_text(text)
            if price is not None:
                return PriceResult(product_url=page.url, price_raw=text, price_value=price)
        except TimeoutError:
            continue
        except Error:
            continue

    html = page.content()
    # Часто цена есть в JSON фрагментах внутри hydration-данных.
    patterns = [
        r'"finalPrice"\s*:\s*"?(\d{2,10})"?',
        r'"price"\s*:\s*"?(\d{2,10})"?',
        r'"cardPrice"\s*:\s*"?(\d{2,10})"?',
    ]
    for pattern in patterns:
        m = re.search(pattern, html)
        if m:
            value = int(m.group(1))
            return PriceResult(product_url=page.url, price_raw=str(value), price_value=value)

    raise RuntimeError("Не удалось извлечь цену. Проверьте валидность URL и авторизацию.")


def get_price(url: str, storage_state_path: Path, browser_name: str, timeout_ms: int, headful: bool) -> PriceResult:
    with sync_playwright() as playwright:
        context = create_context(
            playwright=playwright,
            browser_name=browser_name,
            headful=headful,
            storage_state=storage_state_path,
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

        result = extract_price(page, timeout_ms=timeout_ms)
        context.close()
        return result


def main() -> int:
    args = parse_args()
    storage_state_path = Path(args.storage_state)

    try:
        with sync_playwright() as playwright:
            context = create_context(
                playwright=playwright,
                browser_name=args.browser,
                headful=True if args.save_storage_state else args.headful,
                storage_state=storage_state_path if storage_state_path.exists() else None,
            )
            if args.save_storage_state:
                ensure_logged_in_state(
                    context=context,
                    storage_state_path=storage_state_path,
                    timeout_ms=args.timeout_ms,
                )
                context.close()
                return 0
            context.close()

        result = get_price(
            url=args.url,
            storage_state_path=storage_state_path,
            browser_name=args.browser,
            timeout_ms=args.timeout_ms,
            headful=args.headful,
        )

        if args.json:
            print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        else:
            print(result.price_value)
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
