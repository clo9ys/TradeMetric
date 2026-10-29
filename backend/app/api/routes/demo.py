import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_uow
from app.db.models import Calculation, InstrumentSnapshot
from app.db.uow import UnitOfWork
from app.domain.errors import IncompleteMarketDataError, InvalidCalculationError, StaleMarketDataError
from app.services.calculation import CalculationService, TradeRequest
from app.services.market_data import MOSCOW, MarketDataService, snapshot_to_data
from scripts.demo_calculation import DEMO_BONDS, DEMO_EMAIL, NoNetworkProvider, demo_isin

router = APIRouter(prefix="/api/demo", tags=["demo"])
DEMO_ISINS = {demo_isin(str(bond["isin_prefix"])) for bond in DEMO_BONDS}
DEMO_ISSUERS = {
    demo_isin(str(bond["isin_prefix"])): str(bond["issuer_name"]) for bond in DEMO_BONDS
}


class DemoTrade(BaseModel):
    isin: str
    quantity: int


class DemoCalculationRequest(BaseModel):
    trades: list[DemoTrade] = Field(min_length=1)


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
                "issuer_name": trade.snapshot.issuer_name or DEMO_ISSUERS.get(trade.snapshot.isin),
                "currency": trade.snapshot.currency,
                "coupon_type": trade.snapshot.coupon_type,
                "quantity": trade.quantity,
                "fair_value_rub": str(trade.current_fair_value),
                "dv01_rub": str(trade.dv01),
            }
            for trade in trades
        ],
    }


async def get_demo_snapshots(uow: UnitOfWork) -> dict[str, InstrumentSnapshot]:
    today = datetime.now(MOSCOW).date()
    async with uow as unit:
        rows = await unit.snapshots.get_fetched_on_date(sorted(DEMO_ISINS), today)
    result: dict[str, InstrumentSnapshot] = {}
    for row in rows:
        if row.isin not in result and row.source == "demo":
            try:
                snapshot_to_data(row).validate_freshness(
                    calculation_date=today, last_trading_date=today
                )
            except (IncompleteMarketDataError, StaleMarketDataError):
                continue
            result[row.isin] = row
    return result


@router.get("/instruments")
async def instruments(uow: Annotated[UnitOfWork, Depends(get_uow)]) -> dict[str, object]:
    snapshots = await get_demo_snapshots(uow)
    return {
        "source": "demo",
        "instruments": [
            {
                "isin": isin,
                "issue_name": snapshots[isin].issue_name,
                "issuer_name": snapshots[isin].issuer_name or DEMO_ISSUERS[isin],
                "currency": snapshots[isin].currency,
                "coupon_type": snapshots[isin].coupon_type,
                "default_quantity": bond["quantity"],
            }
            for bond in DEMO_BONDS
            if (isin := demo_isin(str(bond["isin_prefix"]))) in snapshots
        ],
    }


@router.get("/history")
async def history(
    request: Request,
) -> dict[str, object]:
    async with UnitOfWork(request.app.state.db.session_factory) as unit:
        user = await unit.users.get_by_email(DEMO_EMAIL)
        if user is None:
            return {"calculations": []}
        recent = await unit.calculations.list_for_user(user.id, limit=20)
        calculations = [
            await unit.calculations.get_for_user(item.id, user.id) for item in recent
        ]
        return {
            "calculations": [serialize_calculation(item) for item in calculations if item is not None]
        }


@router.post("/calculate")
async def calculate_demo(
    payload: DemoCalculationRequest,
    request: Request,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> dict[str, object]:
    if any(trade.isin not in DEMO_ISINS for trade in payload.trades):
        raise HTTPException(400, "В демо доступны только три тестовых ISIN")
    available = await get_demo_snapshots(uow)
    if any(trade.isin not in available for trade in payload.trades):
        raise HTTPException(409, "Демо-снимки за сегодня не найдены. Запустите demo_calculation.py")

    async with UnitOfWork(request.app.state.db.session_factory) as unit:
        user = await unit.users.get_by_email(DEMO_EMAIL)
    if user is None:
        raise HTTPException(409, "Демо-пользователь не найден. Запустите demo_calculation.py")

    market_data = MarketDataService(
        UnitOfWork(request.app.state.db.session_factory), NoNetworkProvider()
    )
    service = CalculationService(UnitOfWork(request.app.state.db.session_factory), market_data)
    try:
        result = await service.calculate(
            user.id,
            [
                TradeRequest(client_trade_id=uuid.uuid4(), isin=trade.isin, quantity=trade.quantity)
                for trade in payload.trades
            ],
            last_trading_date=datetime.now(MOSCOW).date(),
        )
    except (InvalidCalculationError, IncompleteMarketDataError, StaleMarketDataError) as error:
        raise HTTPException(400, str(error)) from error
    return {
        "calculation_id": str(result.id),
        "source": "demo",
        "currency": "RUB",
        "total_dv01_rub": str(result.total_dv01_rub),
        "total_fair_value_rub": str(
            sum((trade.metrics.current_fair_value_rub for trade in result.trades), Decimal(0))
        ),
        "trades": [
            {
                "isin": trade.isin,
                "issue_name": available[trade.isin].issue_name,
                "issuer_name": available[trade.isin].issuer_name or DEMO_ISSUERS[trade.isin],
                "currency": available[trade.isin].currency,
                "coupon_type": available[trade.isin].coupon_type,
                "quantity": trade.quantity,
                "fair_value_rub": str(trade.metrics.current_fair_value_rub),
                "dv01_rub": str(trade.metrics.dv01_rub),
            }
            for trade in result.trades
        ],
    }
