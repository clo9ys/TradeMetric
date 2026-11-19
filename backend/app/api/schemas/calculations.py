import uuid
from datetime import date

from pydantic import BaseModel, Field, StrictInt


class CalculationTradeInput(BaseModel):
    client_trade_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    isin: str
    quantity: StrictInt


class CalculationInput(BaseModel):
    last_trading_date: date
    trades: list[CalculationTradeInput] = Field(min_length=1)
