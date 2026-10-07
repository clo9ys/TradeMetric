# TradeMetric

Модуль расчёта DV01 для гипотетических сделок с облигациями (кейс 3)

Пользователь вводит ISIN и количество бумаг, добавляет несколько сделок и запускает расчёт. Бэкенд берёт рыночные данные из Cbonds (если бумаги там нет, то из RU Data), сохраняет снимок в Postgres и считает DV01 SQL-функцией прямо в базе

```
DV01 = FV * (-Dmod * 1bp + 0.5 * Convexity * 1bp^2),  1bp = 0.0001
```

Для флоатеров Dmod = 1 / число купонов в год, Convexity = 0

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL. Зависимости ставим через uv

## Что где лежит

```
backend/
  app/
    api/          роуты и pydantic-схемы
    services/     auth, расчёт, рыночные данные
    providers/    адаптеры Cbonds и RU Data
    domain/       enums, ошибки, проверка ISIN
    db/           модели, репозитории, UnitOfWork, DatabaseManager
  scripts/        create_user.py (регистрации нет, аккаунты заводит админ)
  tests/          unit, integration, fixtures с ответами поставщиков
frontend/
```

## Запуск

Пока можно только поставить зависимости:

```
cd backend
uv sync
```

Docker-compose, миграции и запуск сервера допишем, когда они появятся

## Команда

- Полина Журавлева: TeamLead
- Искандер Хамматов: Frontend
- Максим Столповский: Backend (server logic), DevOps
- Дарья Новикова: Backend (business logic), testing
