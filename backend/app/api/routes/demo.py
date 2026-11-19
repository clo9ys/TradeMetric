import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StrictInt

from app.api.deps import get_calculation_service, get_market_data_service
from app.config import get_settings
from app.db.models import Calculation, InstrumentSnapshot
from app.db.uow import UnitOfWork
from app.domain.errors import InvalidCalculationError
from app.services.calculation import CalculationService, TradeRequest
from app.services.market_data import MOSCOW, MarketDataService
from scripts.demo_calculation import DEMO_EMAIL, DEMO_TRADES

router = APIRouter(prefix="/api/demo", tags=["demo"])
DEMO_ISINS = {isin for isin, _ in DEMO_TRADES}


class DemoTrade(BaseModel):
    isin: str
    quantity: StrictInt


class DemoCalculationRequest(BaseModel):
    trades: list[DemoTrade] = Field(min_length=1)


def demo_date():
    settings = get_settings()
    if settings.bond_data_source != "csv" or settings.csv_data_mode != "demo":
        raise HTTPException(409, "Для демо нужны BOND_DATA_SOURCE=csv и CSV_DATA_MODE=demo")
    if settings.demo_last_trading_date is None:
        raise HTTPException(409, "Укажите DEMO_LAST_TRADING_DATE: дату котировок учебного CSV")
    return settings.demo_last_trading_date


def serialize_calculation(calculation: Calculation) -> dict[str, object]:
    trades = calculation.trades
    return {
        "calculation_id": str(calculation.id),
        "calculated_at": calculation.calculated_at.isoformat(),
        "source": "demo",
        "currency": "RUB",
        "total_dv01_rub": str(sum((trade.dv01 for trade in trades), Decimal(0))),
        "total_fair_value_rub": str(
            sum((trade.current_fair_value for trade in trades), Decimal(0))
        ),
        "trades": [
            {
                "isin": trade.snapshot.isin,
                "issue_name": trade.snapshot.issue_name,
                "issuer_name": trade.snapshot.issuer_name,
                "currency": trade.snapshot.currency,
                "coupon_type": trade.snapshot.coupon_type,
                "quantity": trade.quantity,
                "fair_value_rub": str(trade.current_fair_value),
                "dv01_rub": str(trade.dv01),
                "fx_rate_rub": str(trade.fx_rate_rub),
                "fx_source": trade.fx_source,
                "fx_effective_date": str(trade.fx_effective_date),
                "fx_fetched_at": (
                    trade.fx_snapshot.fetched_at.isoformat() if trade.fx_snapshot else None
                ),
            }
            for trade in trades
        ],
    }


async def get_demo_snapshots(market: MarketDataService) -> dict[str, InstrumentSnapshot]:
    prepared = await market.prepare_snapshots(
        sorted(DEMO_ISINS),
        calculation_date=datetime.now(MOSCOW).date(),
        last_trading_date=demo_date(),
    )
    return prepared.snapshots


@router.get("/instruments")
async def instruments(
    market: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> dict[str, object]:
    snapshots = await get_demo_snapshots(market)
    return {
        "source": "demo",
        "instruments": [
            {
                "isin": isin,
                "issue_name": snapshots[isin].issue_name,
                "issuer_name": snapshots[isin].issuer_name,
                "currency": snapshots[isin].currency,
                "coupon_type": snapshots[isin].coupon_type,
                "default_quantity": quantity,
            }
            for isin, quantity in DEMO_TRADES
        ],
    }


@router.get("/history")
async def history(request: Request) -> dict[str, object]:
    demo_date()
    async with UnitOfWork(request.app.state.db.session_factory) as unit:
        user = await unit.users.get_by_email(DEMO_EMAIL)
        if user is None:
            return {"calculations": []}
        recent = await unit.calculations.list_for_user(user.id, limit=20)
        calculations = [await unit.calculations.get_for_user(item.id, user.id) for item in recent]
        return {"calculations": [serialize_calculation(item) for item in calculations if item]}


@router.post("/calculate")
async def calculate_demo(
    payload: DemoCalculationRequest,
    request: Request,
    service: Annotated[CalculationService, Depends(get_calculation_service)],
) -> dict[str, object]:
    last_trading_date = demo_date()
    if any(trade.isin not in DEMO_ISINS for trade in payload.trades):
        raise InvalidCalculationError("В демо доступны только три тестовых ISIN")
    async with UnitOfWork(request.app.state.db.session_factory) as unit:
        user = await unit.users.get_by_email(DEMO_EMAIL)
    if user is None:
        raise HTTPException(
            409, "Демо-пользователь не найден. Запустите python -m scripts.demo_calculation"
        )
    result = await service.calculate(
        user.id,
        [TradeRequest(uuid.uuid4(), trade.isin, trade.quantity) for trade in payload.trades],
        last_trading_date=last_trading_date,
    )
    async with UnitOfWork(request.app.state.db.session_factory) as unit:
        saved = await unit.calculations.get_for_user(result.id, user.id)
        return serialize_calculation(saved)
