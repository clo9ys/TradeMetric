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

## База в Docker

Postgres поднимается через docker compose, все команды из **корня репо**. Логин, пароль и имя базы он берёт из того же `.env`

```
docker compose up -d        # поднять в фоне
docker compose ps           # в STATUS должно быть healthy
docker compose logs db      # если что-то не так
docker compose stop         # остановить, данные остаются
docker compose down -v      # снести вместе с данными, база будет пустой
```

После первого запуска или `down -v` накатываем миграции из `backend/`: `uv run alembic upgrade head`

Зайти в psql: `docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB>`

Если порт 5432 занят своим Postgres на машине, поменяй порт слева в `ports` в `docker-compose.yml` и `POSTGRES_PORT` в `.env`

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

## Первый пользователь

Регистрации нет, аккаунты заводим скриптом из `backend/`:

```
uv run python -m scripts.create_user max@example.com
```

Пароль скрипт спросит сам, дважды, не короче 8 символов. Email приводится к нижнему регистру

## Запуск сервера

```
uv run uvicorn app.main:app --reload
```

Документация API: http://127.0.0.1:8000/docs, проверка базы: `GET /api/health`

Вход работает через cookie сессии. В `/docs` после `POST /api/auth/login` браузер сохранит её сам. Для `POST`-запросов, кроме логина, нужен заголовок `X-CSRF-Token`: его значение приходит в ответе `login` и `me`

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
