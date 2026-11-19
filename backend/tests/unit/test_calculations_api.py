import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_calculation_service, require_csrf
from app.api.errors import register_error_handlers
from app.api.routes.calculations import router
from app.services.calculation import CalculationService
from tests.unit.test_calculation_service import NOW, FakeFXProvider, FakeMarketData, FakeUnitOfWork


@pytest.fixture
async def api():
    app = FastAPI()
    app.include_router(router)
    register_error_handlers(app)
    service = CalculationService(
        FakeUnitOfWork(), FakeMarketData(), FakeFXProvider(), clock=lambda: NOW
    )
    app.dependency_overrides[get_calculation_service] = lambda: service
    app.dependency_overrides[require_csrf] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_calculation_api_serializes_decimal_and_provenance(api):
    response = await api.post(
        "/api/calculations",
        json={
            "last_trading_date": "2026-10-23",
            "trades": [
                {"isin": "XS0157815647", "quantity": 3},
                {"isin": "XS0157815647", "quantity": -1},
            ],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result["total_dv01_rub"], str)
    assert len(result["trades"]) == 2
    assert result["trades"][0]["market_data_source"] == "cbonds"
    assert result["trades"][0]["fx_rate"] == {
        "rub_per_unit": "80.5",
        "effective_date": "2026-10-23",
        "source": "CBR",
        "currency": "USD",
        "fetched_at": "2026-10-25T12:00:00Z",
    }
    assert result["trades"][0]["snapshot_id"] == result["trades"][1]["snapshot_id"]


@pytest.mark.parametrize("quantity", [True, 1.5, "10"])
async def test_api_does_not_coerce_quantity(api, quantity):
    response = await api.post(
        "/api/calculations",
        json={
            "last_trading_date": "2026-10-23",
            "trades": [{"isin": "XS0157815647", "quantity": quantity}],
        },
    )
    assert response.status_code == 422


async def test_domain_error_has_understandable_detail(api):
    response = await api.post(
        "/api/calculations",
        json={
            "last_trading_date": "2026-10-23",
            "trades": [{"isin": "XS0157815647", "quantity": 0}],
        },
    )
    assert response.status_code == 400
    assert "ненулевым целым" in response.json()["detail"]


async def test_calculation_route_is_registered_in_application():
    from app.main import create_app

    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")
    assert "/api/calculations" in response.json()["paths"]
