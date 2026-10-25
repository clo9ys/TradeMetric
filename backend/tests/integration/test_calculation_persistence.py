import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import InstrumentSnapshot
from app.db.uow import UnitOfWork
from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.market_data import NormalizedBondData
from app.services.calculation import (
    CalculationService,
    TradeRequest,
    calculate_total_dv01,
    calculate_trade_metrics,
)
from app.services.market_data import MarketDataService, snapshot_to_data


@pytest.fixture
async def database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")

    engine = create_async_engine(url)
    schema = f"dv01_test_{uuid.uuid4().hex}"
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"SET search_path TO {schema}"))
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            config.attributes["connection"] = connection.sync_connection
            await connection.run_sync(lambda _: command.upgrade(config, "head"))
            yield connection
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    finally:
        await engine.dispose()


async def insert_snapshot(
    connection: AsyncConnection,
    *,
    isin: str,
    currency: str = "RUB",
    quote_kind: str = "percent",
    quote_value: str = "101.25",
    price_type: str = "clean",
    accrued: str = "12.3",
    coupon_type: str = "fixed",
    frequency: int | None = None,
    duration: str | None = "4.2",
    convexity: str | None = "19.5",
) -> uuid.UUID:
    return (
        await connection.execute(
            text(
                """
                INSERT INTO instrument_snapshots (
                    isin, source, quote_source, price_type, quote_as_of_date,
                    risk_as_of_date, accrued_as_of_date, fetched_at, currency,
                    nominal_per_bond, quote_kind, quote_value, accrued_per_bond,
                    coupon_type, coupon_frequency, modified_duration, convexity
                ) VALUES (
                    :isin, 'cbonds', 'synthetic integration test', :price_type,
                    :as_of_date, :risk_as_of_date, :accrued_as_of_date, :fetched_at,
                    :currency, 1000, :quote_kind, :quote_value, :accrued,
                    :coupon_type, :frequency, :duration, :convexity
                ) RETURNING id
                """
            ),
            {
                "isin": isin,
                "price_type": price_type,
                "as_of_date": date(2026, 10, 23),
                "risk_as_of_date": date(2026, 10, 23) if coupon_type == "fixed" else None,
                "accrued_as_of_date": date(2026, 10, 23) if price_type == "clean" else None,
                "fetched_at": datetime(2026, 10, 25, tzinfo=UTC),
                "currency": currency,
                "quote_kind": quote_kind,
                "quote_value": Decimal(quote_value),
                "accrued": Decimal(accrued),
                "coupon_type": coupon_type,
                "frequency": frequency,
                "duration": Decimal(duration) if duration is not None else None,
                "convexity": Decimal(convexity) if convexity is not None else None,
            },
        )
    ).scalar_one()


async def test_python_calculation_with_postgresql_snapshots_and_saved_trades(
    database: AsyncConnection,
):
    assert (
        await database.scalar(
            text("SELECT to_regprocedure('calculate_trade_metrics(uuid,bigint,numeric)')")
        )
        is None
    )
    fixed_clean = await insert_snapshot(database, isin="RU000A10D4Y2")
    fixed_dirty_fx = await insert_snapshot(
        database,
        isin="XS0157815647",
        currency="USD",
        quote_kind="amount",
        quote_value="1043.125",
        price_type="dirty",
        accrued="23.4",
        duration="2",
        convexity="10",
    )
    floating = await insert_snapshot(
        database,
        isin="RU000A10D4Z9",
        quote_kind="amount",
        quote_value="997.75",
        accrued="1.25",
        coupon_type="floating",
        frequency=4,
        duration=None,
        convexity=None,
    )

    async with AsyncSession(bind=database, join_transaction_mode="create_savepoint") as session:
        bonds = {}
        for snapshot_id in (fixed_clean, fixed_dirty_fx, floating):
            snapshot = await session.get(InstrumentSnapshot, snapshot_id)
            assert snapshot is not None
            bonds[snapshot_id] = snapshot_to_data(snapshot)

    user_id = (
        await database.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('dv01@example.test', 'test') RETURNING id"
            )
        )
    ).scalar_one()
    calculation_id = (
        await database.execute(
            text(
                """
                INSERT INTO calculations (
                    user_id, requested_at, calculated_at, methodology_version, data_policy_version
                ) VALUES (:user_id, :now, :now, 'python-v1', 'test-v1') RETURNING id
                """
            ),
            {"user_id": user_id, "now": datetime(2026, 10, 25, tzinfo=UTC)},
        )
    ).scalar_one()

    lines = [
        (1, fixed_clean, 3, Decimal("1")),
        (2, fixed_dirty_fx, -2, Decimal("80.5")),
        (3, fixed_clean, -1, Decimal("1")),
        (4, floating, 4, Decimal("1")),
    ]
    metrics = []
    for line_number, snapshot_id, quantity, fx_rate in lines:
        result = calculate_trade_metrics(bonds[snapshot_id], quantity, fx_rate)
        metrics.append(result)
        await database.execute(
            text(
                """
                INSERT INTO calculation_trades (
                    calculation_id, snapshot_id, client_trade_id, line_number, quantity,
                    current_fair_value, duration_used, convexity_used, dv01
                ) VALUES (
                    :calculation_id, :snapshot_id, :client_trade_id, :line_number,
                    :quantity, :fair_value, :duration, :convexity, :dv01
                )
                """
            ),
            {
                "calculation_id": calculation_id,
                "snapshot_id": snapshot_id,
                "client_trade_id": uuid.uuid4(),
                "line_number": line_number,
                "quantity": quantity,
                "fair_value": result.current_fair_value_rub,
                "duration": result.duration_used,
                "convexity": result.convexity_used,
                "dv01": result.dv01_rub,
            },
        )

    rows = (
        (
            await database.execute(
                text(
                    """
                SELECT line_number, snapshot_id, quantity, current_fair_value,
                       duration_used, convexity_used, dv01
                FROM calculation_trades WHERE calculation_id = :calculation_id
                ORDER BY line_number
                """
                ),
                {"calculation_id": calculation_id},
            )
        )
        .mappings()
        .all()
    )

    assert len(rows) == 4
    assert rows[0]["snapshot_id"] == rows[2]["snapshot_id"] == fixed_clean
    assert [row["quantity"] for row in rows] == [3, -2, -1, 4]
    assert metrics[0].dirty_price_per_bond == Decimal("1024.8")
    assert metrics[1].dirty_price_per_bond == Decimal("1043.125")
    assert metrics[1].current_fair_value_rub == Decimal("-167943.125")
    assert metrics[3].duration_used == Decimal("0.25")
    assert metrics[3].convexity_used == 0
    for row, result in zip(rows, metrics, strict=True):
        assert row["current_fair_value"] == result.current_fair_value_rub
        assert row["duration_used"] == result.duration_used
        assert row["convexity_used"] == result.convexity_used
        assert row["dv01"] == result.dv01_rub
    assert calculate_total_dv01(metrics) == sum((row["dv01"] for row in rows), Decimal(0))


class FakeBondProvider:
    def __init__(self):
        self.calls = []

    async def get_bond(self, isin):
        self.calls.append(isin)
        return NormalizedBondData(
            isin=isin,
            source=MarketDataSource.CBONDS,
            currency="RUB",
            nominal_per_bond=Decimal("1000"),
            quote_kind=QuoteKind.PERCENT,
            quote_value=Decimal("101.25"),
            price_type=PriceType.CLEAN,
            quote_source="synthetic integration test",
            quote_as_of_date=date(2026, 10, 23),
            coupon_type=CouponType.FIXED,
            fetched_at=datetime(2026, 10, 25, 12, tzinfo=UTC),
            accrued_per_bond=Decimal("12.3"),
            accrued_as_of_date=date(2026, 10, 23),
            modified_duration=Decimal("4.2"),
            convexity=Decimal("19.5"),
            risk_as_of_date=date(2026, 10, 23),
        )


def calculation_service(connection: AsyncConnection, provider: FakeBondProvider):
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    uow = UnitOfWork(factory)
    market_data = MarketDataService(uow, provider)
    return CalculationService(
        uow,
        market_data,
        clock=lambda: datetime(2026, 10, 25, 12, tzinfo=UTC),
    )


async def test_service_commits_each_line_and_reuses_snapshot_on_second_run(
    database: AsyncConnection,
):
    user_id = (
        await database.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('service@example.test', 'test') RETURNING id"
            )
        )
    ).scalar_one()
    provider = FakeBondProvider()
    service = calculation_service(database, provider)
    isin = "RU000A10D4Y2"
    lines = [TradeRequest(uuid.uuid4(), isin, 3), TradeRequest(uuid.uuid4(), isin, -1)]

    first = await service.calculate(user_id, lines, last_trading_date=date(2026, 10, 23))
    second = await service.calculate(user_id, lines, last_trading_date=date(2026, 10, 23))

    assert provider.calls == [isin]
    assert first.trades[0].snapshot_id == first.trades[1].snapshot_id
    assert second.trades[0].snapshot_id == first.trades[0].snapshot_id
    assert first.total_dv01_rub == second.total_dv01_rub
    assert await database.scalar(text("SELECT COUNT(*) FROM instrument_snapshots")) == 1
    assert await database.scalar(text("SELECT COUNT(*) FROM calculations")) == 2
    assert await database.scalar(text("SELECT COUNT(*) FROM calculation_trades")) == 4
    assert (
        await database.scalar(
            text(
                "SELECT COUNT(*) FROM calculation_trades "
                "WHERE fx_rate_rub = 1 AND fx_source = 'RUB'"
            )
        )
        == 4
    )


async def test_service_rolls_back_new_snapshot_when_calculation_insert_fails(
    database: AsyncConnection,
):
    provider = FakeBondProvider()
    service = calculation_service(database, provider)
    missing_user_id = uuid.uuid4()
    lines = [TradeRequest(uuid.uuid4(), "RU000A10D4Y2", 1)]

    with pytest.raises(IntegrityError):
        await service.calculate(
            missing_user_id,
            lines,
            last_trading_date=date(2026, 10, 23),
        )

    assert provider.calls == ["RU000A10D4Y2"]
    assert await database.scalar(text("SELECT COUNT(*) FROM instrument_snapshots")) == 0
    assert await database.scalar(text("SELECT COUNT(*) FROM calculations")) == 0
    assert await database.scalar(text("SELECT COUNT(*) FROM calculation_trades")) == 0
