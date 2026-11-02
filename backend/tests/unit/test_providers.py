import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.domain.enums import MarketDataSource, PriceType, QuoteKind
from app.domain.errors import (
    IncompleteMarketDataError,
    InstrumentNotFoundError,
    ProviderUnavailableError,
)
from app.providers.cbonds import CbondsAdapter, normalize_cbonds
from app.providers.http import post_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ISIN = "RU000A10D4Y2"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def synthetic_cbonds_responses() -> tuple[dict[str, object], dict[str, object]]:
    emission = {
        "id": "42",
        "isin_code": ISIN,
        "currency_name": "RUB",
        "outstanding_nominal_price": "1000",
        "floating_rate": "0",
    }
    trading = {
        "isin_code": ISIN,
        "emission_id": "42",
        "date": "2026-10-23",
        "dirty_price_currency": "986.12",
        "dur_mod": "4.5",
        "convexity": "25.0",
        "trading_ground_name_eng": "Synthetic exchange",
    }
    return emission, trading


def test_real_cbonds_demo_fixtures_are_not_combined() -> None:
    emission = fixture("cbonds_emission_demo.json")["items"][0]
    trading = fixture("cbonds_trading_demo.json")["items"][0]

    with pytest.raises(IncompleteMarketDataError, match="другого ISIN"):
        normalize_cbonds(emission["isin_code"], emission, trading, fetched_at=datetime.now(UTC))


def test_synthetic_cbonds_complete_snapshot() -> None:
    emission, trading = synthetic_cbonds_responses()
    bond = normalize_cbonds(ISIN, emission, trading, fetched_at=datetime.now(UTC))

    assert bond.source is MarketDataSource.CBONDS
    assert bond.quote_kind is QuoteKind.AMOUNT
    assert bond.price_type is PriceType.DIRTY
    assert bond.quote_value == Decimal("986.12")
    assert bond.modified_duration == Decimal("4.5")
    assert bond.risk_as_of_date == date(2026, 10, 23)


def test_synthetic_cbonds_rejects_missing_risk_field() -> None:
    emission, trading = synthetic_cbonds_responses()
    trading.pop("convexity")

    with pytest.raises(IncompleteMarketDataError, match="выпуклость"):
        normalize_cbonds(ISIN, emission, trading, fetched_at=datetime.now(UTC))


@pytest.mark.asyncio
async def test_cbonds_real_demo_missing_trading_is_incomplete() -> None:
    emission = fixture("cbonds_emission_demo.json")

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("get_emissions/"):
            return httpx.Response(200, json=emission)
        return httpx.Response(200, json={"count": 0, "total": 0, "items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = CbondsAdapter(login=uuid.uuid4().hex, password=uuid.uuid4().hex, client=client)
        with pytest.raises(IncompleteMarketDataError, match="нет котировки"):
            await adapter.get_bond("US037833EL06")


@pytest.mark.asyncio
async def test_cbonds_not_found_is_distinct_from_incomplete() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"count": 0, "total": 0, "items": []})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CbondsAdapter(login=uuid.uuid4().hex, password=uuid.uuid4().hex, client=client)
        with pytest.raises(InstrumentNotFoundError):
            await adapter.get_bond(ISIN)


@pytest.mark.asyncio
async def test_cbonds_embedded_error_is_unavailable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"error": {"err_no": 900000}})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CbondsAdapter(login=uuid.uuid4().hex, password=uuid.uuid4().hex, client=client)
        with pytest.raises(ProviderUnavailableError):
            await adapter.get_bond(ISIN)


@pytest.mark.asyncio
async def test_synthetic_cbonds_http_flow_sorts_tradings() -> None:
    emission, trading = synthetic_cbonds_responses()
    paths = []
    credential = uuid.uuid4().hex

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        payload = json.loads(request.content)
        assert payload["auth"] == {"login": credential, "password": credential}
        assert payload["filters"][0]["value"] == ISIN
        if request.url.path.endswith("get_emissions/"):
            return httpx.Response(200, json={"items": [emission]})
        assert payload["sorting"] == [{"field": "date", "order": "desc"}]
        return httpx.Response(200, json={"items": [trading]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = CbondsAdapter(login=credential, password=credential, client=client)
        bond = await adapter.get_bond(ISIN)
    assert bond.quote_value == Decimal("986.12")
    assert paths == ["/services/json/get_emissions/", "/services/json/get_tradings/"]


@pytest.mark.asyncio
async def test_missing_credentials_do_not_start_http_request() -> None:
    with pytest.raises(ProviderUnavailableError, match="не настроен"):
        await CbondsAdapter(login=None, password=None).get_bond(ISIN)


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
@pytest.mark.asyncio
async def test_http_status_is_provider_unavailable(status: int) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderUnavailableError, match=f"HTTP {status}"):
            await post_json(client, "https://example.invalid", {})


@pytest.mark.asyncio
async def test_http_timeout_is_provider_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ProviderUnavailableError):
            await post_json(client, "https://example.invalid", {})
