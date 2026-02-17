# Ozon price parser (authorized)

Скрипт получает цену товара на `ozon.ru` с учётом авторизации (скидки/акции аккаунта).

## Что делает
- принимает ссылку на карточку товара;
- использует Playwright и авторизованную сессию (`storage_state.json`);
- возвращает цену числом (в рублях) или JSON.

## Установка (Linux VPS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Подготовка авторизованной сессии

### Вариант A: сразу на VPS (если есть GUI/проброс X)
```bash
python ozon_price_monitor.py "https://www.ozon.ru/" --save-storage-state --headful --storage-state ozon_storage_state.json
```

Откроется браузер. Войдите в аккаунт Ozon и нажмите `Enter` в терминале — сессия сохранится.

### Вариант B: первичная сессия на Windows (рекомендуется)
1. Установите Python + Playwright на Windows.
2. Запустите ту же команду с `--save-storage-state`.
3. После логина получите файл `ozon_storage_state.json`.
4. Скопируйте его на VPS (например, `scp`).

Пример:
```bash
scp ozon_storage_state.json user@your-vps:/opt/ozon-monitor/
```

## Использование на VPS

```bash
python ozon_price_monitor.py "https://www.ozon.ru/product/.../" --storage-state ozon_storage_state.json
```

Вывод: только цена числом, например:
```text
12990
```

JSON-режим:
```bash
python ozon_price_monitor.py "https://www.ozon.ru/product/.../" --storage-state ozon_storage_state.json --json
```

## Полезно для cron

```bash
*/15 * * * * cd /opt/ozon-monitor && /opt/ozon-monitor/.venv/bin/python ozon_price_monitor.py "https://www.ozon.ru/product/.../" --storage-state ozon_storage_state.json >> price.log 2>&1
```

## Замечания
- Если Ozon разлогинил сессию, повторите шаг `--save-storage-state`.
- Для получения «персональной» цены скрипт должен запускаться с актуальным `storage_state` вашего аккаунта.
- При необходимости можно сменить движок: `--browser firefox`.
