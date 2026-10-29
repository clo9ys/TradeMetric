import asyncio
import secrets
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db.engine import DatabaseManager
from app.db.models import InstrumentSnapshot, User
from app.db.uow import UnitOfWork
from app.domain.enums import MarketDataSource
from app.domain.errors import InvalidISINError
from app.domain.isin import validate_isin
from app.security import hash_password
from app.services.calculation import CalculationService, TradeRequest
from app.services.market_data import MOSCOW, MarketDataService

DEMO_EMAIL = "demo-calculation@trademetric.local"
DEMO_BONDS = (
    {
        "isin_prefix": "RUDEMO00001",
        "issue_name": "DEMO fixed clean",
        "issuer_name": "Учебный эмитент 1",
        "quantity": 10,
        "quote_kind": "percent",
        "quote_value": Decimal("101.25"),
        "price_type": "clean",
        "accrued_per_bond": Decimal("12.30"),
        "coupon_type": "fixed",
        "coupon_frequency": None,
        "modified_duration": Decimal("4.2"),
        "convexity": Decimal("19.5"),
    },
    {
        "isin_prefix": "RUDEMO00002",
        "issue_name": "DEMO fixed dirty short",
        "issuer_name": "Учебный эмитент 2",
        "quantity": -5,
        "quote_kind": "amount",
        "quote_value": Decimal("980"),
        "price_type": "dirty",
        "accrued_per_bond": None,
        "coupon_type": "fixed",
        "coupon_frequency": None,
        "modified_duration": Decimal("2.1"),
        "convexity": Decimal("5"),
    },
    {
        "isin_prefix": "RUDEMO00003",
        "issue_name": "DEMO floating clean",
        "issuer_name": "Учебный эмитент 3",
        "quantity": 7,
        "quote_kind": "percent",
        "quote_value": Decimal("99.5"),
        "price_type": "clean",
        "accrued_per_bond": Decimal("4"),
        "coupon_type": "floating",
        "coupon_frequency": 4,
        "modified_duration": None,
        "convexity": None,
    },
)


def demo_isin(prefix: str) -> str:
    """Give a fictional 11-character prefix a valid ISIN check digit"""
    for digit in range(10):
        candidate = f"{prefix}{digit}"
        try:
            return validate_isin(candidate)
        except InvalidISINError:
            continue
    raise AssertionError(f"No ISIN check digit for {prefix}")


def make_snapshot(bond: dict[str, object], today: date, fetched_at: datetime) -> InstrumentSnapshot:
    is_fixed = bond["coupon_type"] == "fixed"
    is_clean = bond["price_type"] == "clean"
    return InstrumentSnapshot(
        isin=demo_isin(str(bond["isin_prefix"])),
        issue_name=str(bond["issue_name"]),
        issuer_name=str(bond["issuer_name"]),
        source=MarketDataSource.DEMO.value,
        quote_source="SYNTHETIC DEMO DATA — NOT CBONDS",
        provider_instrument_id=None,
        price_type=str(bond["price_type"]),
        quote_as_of_date=today,
        risk_as_of_date=today if is_fixed else None,
        accrued_as_of_date=today if is_clean else None,
        fetched_at=fetched_at,
        currency="RUB",
        nominal_per_bond=Decimal("1000"),
        quote_kind=str(bond["quote_kind"]),
        quote_value=bond["quote_value"],
        accrued_per_bond=bond["accrued_per_bond"],
        coupon_type=str(bond["coupon_type"]),
        coupon_frequency=bond["coupon_frequency"],
        modified_duration=bond["modified_duration"],
        convexity=bond["convexity"],
    )


class NoNetworkProvider:
    async def get_bond(self, isin: str) -> None:
        raise AssertionError(f"Cache miss for {isin}: demo must never call a provider")


async def run_demo() -> None:
    db = DatabaseManager(get_settings().database_url)
    try:
        if not await db.ping():
            raise RuntimeError("PostgreSQL is unavailable. Start it before running the demo.")

        now = datetime.now(UTC)
        today = now.astimezone(MOSCOW).date()
        isins = [demo_isin(str(bond["isin_prefix"])) for bond in DEMO_BONDS]

        async with UnitOfWork(db.session_factory) as uow:
            cached = await uow.snapshots.get_fetched_on_date(isins, today)
            available = {item.isin for item in cached if item.source == MarketDataSource.DEMO.value}
            new_snapshots = [
                make_snapshot(bond, today, now)
                for bond, isin in zip(DEMO_BONDS, isins, strict=True)
                if isin not in available
            ]
            if new_snapshots:
                await uow.snapshots.add_many(new_snapshots)
                await uow.commit()

        async with UnitOfWork(db.session_factory) as uow:
            user = await uow.users.get_by_email(DEMO_EMAIL)
            if user is None:
                user = User(
                    email=DEMO_EMAIL,
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                )
                await uow.users.add(user)
                await uow.commit()
            user_id = user.id

        market_data = MarketDataService(UnitOfWork(db.session_factory), NoNetworkProvider())
        prepared = await market_data.prepare_snapshots(
            isins, calculation_date=today, last_trading_date=today
        )
        if prepared.new_snapshots or any(
            snapshot.source != MarketDataSource.DEMO.value
            for snapshot in prepared.snapshots.values()
        ):
            raise AssertionError("The demonstration did not read demo snapshots from the cache")

        calculation = CalculationService(UnitOfWork(db.session_factory), market_data)
        trades = [
            TradeRequest(client_trade_id=uuid.uuid4(), isin=isin, quantity=int(bond["quantity"]))
            for bond, isin in zip(DEMO_BONDS, isins, strict=True)
        ]
        result = await calculation.calculate(user_id, trades, last_trading_date=today)
        expected_total = Decimal("-3.449108320000")
        if result.total_dv01_rub != expected_total:
            raise AssertionError(
                f"DV01 mismatch: expected {expected_total}, got {result.total_dv01_rub}"
            )
        print(f"Demo snapshots in cache: {len(prepared.snapshots)}; newly inserted: {len(new_snapshots)}")
        for trade in result.trades:
            print(
                f"{trade.isin}: quantity={trade.quantity}, "
                f"fair_value_rub={trade.metrics.current_fair_value_rub}, "
                f"dv01_rub={trade.metrics.dv01_rub}"
            )
        print(f"TOTAL DV01 RUB: {result.total_dv01_rub}")
        print(f"Calculation saved in PostgreSQL: {result.id}")
        print("Source: demo; synthetic data; no Cbonds API request")
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(run_demo())
