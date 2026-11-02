from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.domain.errors import FXRateUnavailableError
from app.providers.cbr import CBRRateAdapter

DAILY_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<ValCurs Date="23.10.2026" name="Foreign Currency Market">
  <Valute ID="R01235">
    <CharCode>USD</CharCode><Nominal>1</Nominal><Value>80,5000</Value>
  </Valute>
  <Valute ID="R01375">
    <CharCode>CNY</CharCode><Nominal>10</Nominal><Value>110,0000</Value>
  </Valute>
</ValCurs>"""


@pytest.mark.asyncio
async def test_uses_last_effective_rate_and_divides_by_nominal():
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=DAILY_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = CBRRateAdapter(client=client)
        usd = await adapter.get_rate("USD", date(2026, 10, 25))
        cny = await adapter.get_rate("CNY", date(2026, 10, 25))

    assert usd.rub_per_unit == Decimal("80.5000")
    assert cny.rub_per_unit == Decimal("11.0000")
    assert usd.effective_date == date(2026, 10, 23)
    assert usd.source == "CBR"
    assert len(requests) == 2
    assert requests[0].url.params["date_req"] == "25/10/2026"


@pytest.mark.asyncio
async def test_missing_currency_or_future_rate_is_rejected():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=DAILY_XML))
    ) as client:
        adapter = CBRRateAdapter(client=client)
        with pytest.raises(FXRateUnavailableError, match="не опубликовал"):
            await adapter.get_rate("EUR", date(2026, 10, 25))
        with pytest.raises(FXRateUnavailableError, match="некорректный"):
            await adapter.get_rate("USD", date(2026, 10, 22))


@pytest.mark.asyncio
async def test_http_failure_is_distinct_from_missing_rate():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(FXRateUnavailableError, match="не ответил"):
            await CBRRateAdapter(client=client).get_rate("USD", date(2026, 10, 25))
