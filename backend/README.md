# TradeMetric: бэкенд

FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16. Python 3.12, зависимости ставим через uv

## Установка

```
cd backend
uv sync
```

Настройки лежат в `.env` в **корне репо**, не в `backend/`. Шаблон рядом:

```
cp .env.example .env
```

Нужен запущенный Postgres. docker-compose скоро появится, а пока подойдёт любой Postgres 16, доступы к нему прописываются в `.env`

## Миграции

Все команды из `backend/`

```
uv run alembic upgrade head      # накатить всё
uv run alembic downgrade -1      # откатить последнюю
uv run alembic check             # совпадают ли модели с базой
```

Новая миграция:

```
uv run alembic revision --autogenerate --rev-id 0002 -m "dv01 function"
```

- номера идут по порядку: 0001, 0002, ..., в `down_revision` стоит номер предыдущей
- autogenerate видит только таблицы из моделей. SQL-функции и VIEW пишем руками через `op.execute(...)`, в `downgrade` не забываем `DROP`
- сгенерированный файл всегда читаем глазами перед коммитом

## Тесты и линтер

```
uv run pytest
uv run ruff format . && uv run ruff check --fix .
```

## Что где лежит

```
app/
  config.py         настройки из .env
  security.py       Argon2, токены сессии и CSRF
  db/models/        таблицы по ER-схеме
  db/repositories/  запросы к базе
  db/uow.py         UnitOfWork: одна транзакция на одну операцию
  services/         бизнес-логика
  api/              роуты и pydantic-схемы
migrations/         миграции Alembic
tests/              unit, integration, fixtures
```

## Работа с базой из сервиса

Сервис получает `UnitOfWork` в конструкторе и открывает его на каждую операцию:

```python
async with self._uow as uow:
    user = await uow.users.get_by_email(email)
    ...
    await uow.commit()
```

Без `commit()` всё откатывается при выходе из блока. Репозитории внутри: `uow.users`, `uow.auth_sessions`, `uow.snapshots`, `uow.calculations`

## Нормализованные данные облигации

Оба адаптера возвращают `NormalizedBondData` из `app/domain/market_data.py`. Модель проверяет полноту до сохранения в БД. Все денежные и риск-величины передаются как `Decimal`, без `float`:

- `nominal_per_bond` и `accrued_per_bond` — деньги в валюте облигации за одну бумагу;
- `quote_value` — процент непогашенного номинала при `quote_kind=percent` или деньги в валюте облигации за одну бумагу при `quote_kind=amount`;
- `price_type=clean` требует НКД и его дату, `dirty` не прибавляет НКД повторно;
- `modified_duration`, `convexity` для фиксированного купона обязательны оба параметра и дата риска;
- для плавающего купона нужна `coupon_frequency` — число выплат в год; при расчёте дюрация заменяется на `1 / coupon_frequency`, выпуклость — на ноль;
- `quote_as_of_date`, `risk_as_of_date`, `accrued_as_of_date` и `fetched_at` сохраняются раздельно.

Принятое правило свежести: котировка и риск-параметры фиксированного купона должны относиться к последнему торговому дню перед расчётом или к самому дню расчёта, если он торговый. Сервис передаёт эту дату в `validate_freshness`; модель не угадывает торговый календарь по дню недели. Дата НКД не может быть позже даты расчёта. Правило повторного использования снимка, загруженного сегодня по Москве, реализуется в сервисе кэша отдельно
