import argparse
import asyncio
import secrets
import sys
import uuid
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db.engine import DatabaseManager
from app.db.models import User
from app.db.uow import UnitOfWork
from app.domain.enums import MarketDataSource
from app.providers.cbr import CBRRateAdapter
from app.providers.factory import build_bond_provider
from app.security import hash_password
from app.services.calculation import CalculationService, TradeRequest
from app.services.market_data import MarketDataService

DEMO_EMAIL = "demo-calculation@trademetric.local"
DEMO_TRADES = (("RUDEMO000016", 10), ("RUDEMO000024", -5), ("RUDEMO000032", 7))


async def run_demo(last_trading_date: date) -> None:
    settings = get_settings()
    provider, source = build_bond_provider(settings)
    if source is not MarketDataSource.DEMO:
        raise ValueError("Демонстрация требует BOND_DATA_SOURCE=csv и CSV_DATA_MODE=demo")
    db = DatabaseManager(settings.database_url)
    try:
        if not await db.ping():
            raise RuntimeError("PostgreSQL недоступна. Сначала запустите БД и примените миграции.")
        async with UnitOfWork(db.session_factory) as uow:
            user = await uow.users.get_by_email(DEMO_EMAIL)
            if user is None:
                user = User(
                    email=DEMO_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32))
                )
                await uow.users.add(user)
                await uow.commit()
            user_id = user.id

        market = MarketDataService(UnitOfWork(db.session_factory), provider, source=source)
        service = CalculationService(
            UnitOfWork(db.session_factory), market, CBRRateAdapter.from_settings(settings)
        )
        result = await service.calculate(
            user_id,
            [TradeRequest(uuid.uuid4(), isin, quantity) for isin, quantity in DEMO_TRADES],
            last_trading_date=last_trading_date,
        )
        for trade in result.trades:
            print(
                f"{trade.isin}: quantity={trade.quantity}, "
                f"fair_value_rub={trade.metrics.current_fair_value_rub}, "
                f"dv01_rub={trade.metrics.dv01_rub}, FX={trade.fx_rate}"
            )
        print(f"TOTAL DV01 RUB: {result.total_dv01_rub}")
        print(f"Calculation saved in PostgreSQL: {result.id}")
        print("Source: demo CSV; synthetic data; market dates were NOT changed")
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Расчёт из учебного CSV с сохранением в PostgreSQL"
    )
    parser.add_argument("--last-trading-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    asyncio.run(run_demo(args.last_trading_date))
