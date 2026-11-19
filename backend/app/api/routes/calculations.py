import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import TypeAdapter

from app.api.calculation_view import calculation_view
from app.api.deps import CalculationServiceDep, CsrfSession, CurrentSession, get_uow
from app.api.schemas.calculations import CalculationInput
from app.db.uow import UnitOfWork
from app.services.calculation import CalculationResult, TradeRequest

router = APIRouter(prefix="/api/calculations", tags=["calculations"])


@router.get("")
async def history(
    session: CurrentSession,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    async with uow as unit:
        rows = await unit.calculations.list_for_user(
            session.user.id, limit=limit, offset=offset, with_trades=True
        )
        return {"calculations": [calculation_view(row) for row in rows]}


@router.get("/{calculation_id}")
async def detail(
    calculation_id: uuid.UUID,
    session: CurrentSession,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> dict[str, object]:
    async with uow as unit:
        row = await unit.calculations.get_for_user(calculation_id, session.user.id)
        if row is None:
            raise HTTPException(404, "Расчёт не найден")
        return calculation_view(row)


@router.post("")
async def calculate(
    payload: CalculationInput,
    session: CsrfSession,
    service: CalculationServiceDep,
) -> dict[str, object]:
    result = await service.calculate(
        session.user_id,
        [
            TradeRequest(trade.client_trade_id, trade.isin, trade.quantity)
            for trade in payload.trades
        ],
        last_trading_date=payload.last_trading_date,
    )
    # Pydantic в JSON-режиме представляет Decimal строкой
    return TypeAdapter(CalculationResult).dump_python(result, mode="json")
