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
                "accrued_as_of_date": date(2026, 10, 23),
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


@pytest.fixture
async def csv_fx_service(database, tmp_path):
    import csv

    import httpx

    from app.providers.cbr import CBRRateAdapter
    from app.providers.csv import CsvBondDataProvider
    from tests.unit.test_cbr import DAILY_XML

    sample = Path(__file__).resolve().parents[2] / "data/bonds_demo.csv"
    with sample.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        rows = list(reader)
    for row in rows:
        row["currency"] = "CNY" if row["coupon_type"] == "floating" else "USD"
        for field in ("quote_as_of_date", "risk_as_of_date", "accrued_as_of_date"):
            if row[field]:
                row[field] = "2026-10-23"
    path = tmp_path / "synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    factory = async_sessionmaker(
        bind=database, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    uow = UnitOfWork(factory)
    calls = []

    def respond(request):
        calls.append(request)
        # HTTP происходит вне транзакции записи CalculationService.
        assert uow._session is None
        return httpx.Response(200, content=DAILY_XML)

    now = datetime(2026, 10, 25, 12, tzinfo=UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = CsvBondDataProvider(path, source=MarketDataSource.CSV, clock=lambda: now)
        market = MarketDataService(uow, provider, source=MarketDataSource.CSV)
        service = CalculationService(
            uow, market, CBRRateAdapter(client=client, clock=lambda: now), clock=lambda: now
        )
        yield service, calls


async def test_csv_and_cbr_chain_saves_fx_provenance_and_repeated_rows(database, csv_fx_service):
    service, calls = csv_fx_service
    user_id = (
        await database.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('csv@example.test', 'test') RETURNING id"
            )
        )
    ).scalar_one()
    lines = [
        TradeRequest(uuid.uuid4(), "RUDEMO000016", 3),
        TradeRequest(uuid.uuid4(), "RUDEMO000016", -1),
        TradeRequest(uuid.uuid4(), "RUDEMO000032", 4),
    ]
    result = await service.calculate(user_id, lines, last_trading_date=date(2026, 10, 23))
    assert len(calls) == 2  # Один вызов на уникальную валюту.
    assert result.trades[0].snapshot_id == result.trades[1].snapshot_id
    assert result.trades[2].fx_rate.rub_per_unit == Decimal("11")
    rows = (
        (
            await database.execute(
                text(
                    "SELECT t.quantity, t.fx_snapshot_id, f.currency, "
                    "f.rub_per_unit, f.effective_date, "
                    "f.requested_date, f.fetched_at, f.source FROM calculation_trades t "
                    "JOIN fx_rate_snapshots f ON f.id = t.fx_snapshot_id "
                    "ORDER BY t.line_number"
                )
            )
        )
        .mappings()
        .all()
    )
    assert [row["quantity"] for row in rows] == [3, -1, 4]
    assert rows[0]["fx_snapshot_id"] == rows[1]["fx_snapshot_id"]
    assert {row["currency"] for row in rows} == {"USD", "CNY"}
    assert all(row["effective_date"] == date(2026, 10, 23) for row in rows)
    assert all(row["requested_date"] == date(2026, 10, 25) for row in rows)
    assert all(row["fetched_at"] == datetime(2026, 10, 25, 12, tzinfo=UTC) for row in rows)
    assert all(row["source"] == "CBR" for row in rows)
    assert await database.scalar(text("SELECT count(*) FROM fx_rate_snapshots")) == 2
    assert (
        await database.scalar(
            text("SELECT count(*) FROM instrument_snapshots WHERE source = 'csv'")
        )
        == 2
    )


async def test_last_row_db_failure_rolls_back_bonds_fx_and_calculation(database, csv_fx_service):
    service, calls = csv_fx_service
    user_id = (
        await database.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('rollback@example.test', 'test') RETURNING id"
            )
        )
    ).scalar_one()
    await database.execute(
        text(
            "ALTER TABLE calculation_trades ADD CONSTRAINT test_reject_short CHECK (quantity <> -1)"
        )
    )
    lines = [
        TradeRequest(uuid.uuid4(), "RUDEMO000016", 3),
        TradeRequest(uuid.uuid4(), "RUDEMO000016", -1),
    ]
    with pytest.raises(IntegrityError):
        await service.calculate(user_id, lines, last_trading_date=date(2026, 10, 23))
    assert len(calls) == 1
    for table in (
        "instrument_snapshots",
        "fx_rate_snapshots",
        "calculations",
        "calculation_trades",
    ):
        assert await database.scalar(text(f"SELECT count(*) FROM {table}")) == 0


async def test_model_metadata_matches_migrated_schema(database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.base import Base

    differences = await database.run_sync(
        lambda connection: compare_metadata(MigrationContext.configure(connection), Base.metadata)
    )
    assert differences == []


async def test_demo_script_reads_csv_and_saves_complete_calculation(database, monkeypatch, capsys):
    from types import SimpleNamespace

    from app.config import Settings
    from app.providers.csv import CsvBondDataProvider
    from scripts import demo_calculation as demo

    now = datetime(2026, 11, 19, 12, tzinfo=UTC)
    factory = async_sessionmaker(
        bind=database, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async def ping():
        return True

    async def dispose():
        pass

    monkeypatch.setattr(
        demo,
        "DatabaseManager",
        lambda _: SimpleNamespace(
            session_factory=factory,
            ping=ping,
            dispose=dispose,
        ),
    )
    settings = Settings(
        _env_file=None, postgres_user="test", postgres_password="test", postgres_db="test"
    )
    monkeypatch.setattr(demo, "get_settings", lambda: settings)
    monkeypatch.setattr(
        demo,
        "build_bond_provider",
        lambda settings: (
            CsvBondDataProvider(settings.resolved_csv_path, clock=lambda: now),
            MarketDataSource.DEMO,
        ),
    )
    original_service = demo.CalculationService
    monkeypatch.setattr(
        demo, "CalculationService", lambda *args: original_service(*args, clock=lambda: now)
    )
    await demo.run_demo(date(2026, 11, 19))
    output = capsys.readouterr().out
    assert "TOTAL DV01 RUB: -3.449108320000" in output
    assert "market dates were NOT changed" in output
    assert await database.scalar(text("SELECT count(*) FROM calculation_trades")) == 3
    assert await database.scalar(text("SELECT count(*) FROM fx_rate_snapshots")) == 1


async def test_regular_csv_site_login_calculation_and_private_history(database, monkeypatch):
    from types import SimpleNamespace

    import httpx

    from app.api.deps import get_calculation_service
    from app.config import get_settings
    from app.main import create_app
    from app.providers.csv import CsvBondDataProvider
    from app.security import hash_password

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("BOND_DATA_SOURCE", "csv")
    monkeypatch.setenv("CSV_DATA_MODE", "demo")
    monkeypatch.setenv("CSV_REQUIRE_MANIFEST", "false")
    monkeypatch.setenv(
        "CSV_BONDS_PATH", str(Path(__file__).resolve().parents[2] / "data/bonds_demo.csv")
    )
    get_settings.cache_clear()
    factory = async_sessionmaker(
        bind=database, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    password_hash = hash_password("site-password")
    for email in ("alice@example.com", "bob@example.com"):
        await database.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:email, :hash)"),
            {"email": email, "hash": password_hash},
        )
    now = datetime(2026, 11, 19, 12, tzinfo=UTC)
    provider = CsvBondDataProvider(get_settings().resolved_csv_path, clock=lambda: now)
    market = MarketDataService(UnitOfWork(factory), provider, source=MarketDataSource.DEMO)
    service = CalculationService(UnitOfWork(factory), market, clock=lambda: now)
    app = create_app()
    app.state.db = SimpleNamespace(session_factory=factory)
    app.dependency_overrides[get_calculation_service] = lambda: service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/calculations")).status_code == 401
            assert (await client.get("/api/instruments")).status_code == 401
            assert (await client.get("/api/demo/history")).status_code == 404
            auth = await client.post(
                "/api/auth/login", json={"email": "alice@example.com", "password": "site-password"}
            )
            assert auth.status_code == 200
            catalog = await client.get("/api/instruments")
            assert catalog.status_code == 200
            assert catalog.json()["source"] == "demo"
            assert len(catalog.json()["instruments"]) == 3
            assert catalog.json()["instruments"][0]["quote_as_of_date"] == "2026-11-19"
            body = {
                "last_trading_date": "2026-11-19",
                "trades": [
                    {"isin": "RUDEMO000016", "quantity": 10},
                    {"isin": "RUDEMO000024", "quantity": -5},
                    {"isin": "RUDEMO000032", "quantity": 7},
                ],
            }
            assert (await client.post("/api/calculations", json=body)).status_code == 403
            saved = await client.post(
                "/api/calculations", json=body, headers={"X-CSRF-Token": auth.json()["csrf_token"]}
            )
            assert saved.status_code == 200, saved.text
            calculation_id = saved.json()["id"]
            detail = await client.get(f"/api/calculations/{calculation_id}")
            assert detail.status_code == 200
            assert Decimal(detail.json()["total_dv01_rub"]) == Decimal("-3.44910832")
            assert all(
                row["fx_source"] == "RUB" and row["fx_fetched_at"]
                for row in detail.json()["trades"]
            )
            history = await client.get("/api/calculations")
            assert [row["calculation_id"] for row in history.json()["calculations"]] == [
                calculation_id
            ]
            assert (await client.get("/api/calculations?limit=0")).status_code == 422
            other = await client.post(
                "/api/auth/login", json={"email": "bob@example.com", "password": "site-password"}
            )
            assert other.status_code == 200
            assert (await client.get("/api/calculations")).json() == {"calculations": []}
            assert (await client.get(f"/api/calculations/{calculation_id}")).status_code == 404
    finally:
        get_settings.cache_clear()


async def test_all_100_real_market_isins_are_calculated_and_saved_atomically(database):
    import json

    from app.providers.csv import CsvBondDataProvider

    path = Path(__file__).resolve().parents[2] / "data/bonds_market.csv"
    metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    downloaded_at = datetime.fromisoformat(metadata["downloaded_at"])
    provider = CsvBondDataProvider(
        path, source=MarketDataSource.CSV, clock=lambda: downloaded_at, require_manifest=True
    )
    bonds = await provider.list_bonds()
    factory = async_sessionmaker(
        bind=database, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    service = CalculationService(
        UnitOfWork(factory),
        MarketDataService(UnitOfWork(factory), provider, source=MarketDataSource.CSV),
        clock=lambda: downloaded_at,
    )
    user_id = (
        await database.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('market100@example.com', 'test') RETURNING id"
            )
        )
    ).scalar_one()
    result = await service.calculate(
        user_id,
        [TradeRequest(uuid.uuid4(), bond.isin, 1 if i % 2 else -1) for i, bond in enumerate(bonds)],
        last_trading_date=date.fromisoformat(metadata["market_trade_date"]),
    )
    assert len(result.trades) == 100
    assert result.total_dv01_rub == sum((row.metrics.dv01_rub for row in result.trades), Decimal(0))
    assert (
        await database.scalar(text("SELECT count(*) FROM instrument_snapshots WHERE source='csv'"))
        == 100
    )
    assert await database.scalar(text("SELECT count(*) FROM calculation_trades")) == 100
    assert (
        await database.scalar(text("SELECT count(*) FROM fx_rate_snapshots WHERE currency='RUB'"))
        == 1
    )
