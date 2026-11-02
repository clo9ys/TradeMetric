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

### Локальная демонстрация расчёта

Нужны Docker, Python с установленными зависимостями бэкенда и Node.js 20.19+ или 22.12+. Скопируйте `.env.example` в `.env` и задайте пароль PostgreSQL. Команды ниже используют виртуальное окружение `.venv` в корне репозитория. В PowerShell из корня репозитория запустите БД:

```powershell
docker compose up -d db
```

После первого создания базы примените миграции, затем загрузите синтетические снимки за текущий день. Скрипт также проверяет расчёт; его можно запускать повторно. Повторите загрузку в день показа, поскольку проверяется дата снимка.

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.demo_calculation
```

Проверочный скрипт сохраняет один расчёт в истории при каждом запуске. Чтобы перед показом оставить историю пустой, после загрузки снимков выполните `..\.venv\Scripts\python.exe -m scripts.clear_demo_history --apply` из папки `backend`. Команда удаляет только расчёты технического демо-пользователя; снимки и пользователь остаются.

В этом же терминале запустите API:

```powershell
$env:DEMO_MODE = 'true'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

В другом терминале из корня репозитория:

```powershell
cd frontend
npm ci
npm run dev
```

Откройте `http://127.0.0.1:5173/`, нажмите **«Загрузить демо»**, затем **«Рассчитать»**. Страница покажет DV01, стоимость портфеля и значения по трём сделкам. Это настоящий вызов `CalculationService` и SQL-функции расчёта с данными из кеша PostgreSQL. Снимки синтетические, имеют `source=demo`; запросов к Cbonds API нет. Маршруты `/api/demo/*` доступны только при `DEMO_MODE=true`. Для такой демонстрации запускайте сервер только на `127.0.0.1`.

При запуске из папки `backend` используйте `python -m scripts.demo_calculation` или `python scripts/demo_calculation.py`, если активировано нужное окружение. Команда выше явно использует окружение в корне проекта.

## Команда

- Полина Журавлева: TeamLead + Frontend
- Искандер Хамматов: Frontend
- Максим Столповский: Backend (server logic), DevOps
- Дарья Новикова: Backend (business logic), testing
