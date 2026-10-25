from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import httpx

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import (
    IncompleteMarketDataError,
    InstrumentNotFoundError,
    ProviderUnavailableError,
)
from app.domain.isin import validate_isin
from app.domain.market_data import NormalizedBondData
from app.providers.http import post_json, provider_client

if TYPE_CHECKING:
    from app.config import Settings

CBONDS_BASE_URL = "https://ws2.cbonds.info/services/json"


def _items(response: object) -> list[dict[str, object]]:
    """Проверяет оболочку ответа Cbonds: должен быть словарь со списком items"""
    if not isinstance(response, dict):
        raise IncompleteMarketDataError("Некорректная структура ответа Cbonds")
    if "error" in response:
        raise ProviderUnavailableError("Cbonds отклонил запрос")
    items = response.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise IncompleteMarketDataError("Cbonds не вернул список записей")
    return items


def _decimal(value: object, field: str) -> Decimal:
    if value is None or value == "":
        raise IncompleteMarketDataError(f"Cbonds не вернул {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise IncompleteMarketDataError(f"Cbonds вернул некорректный {field}") from error
    if not result.is_finite():
        raise IncompleteMarketDataError(f"Cbonds вернул некорректный {field}")
    return result


def _date(value: object, field: str) -> date:
    """Берёт первые десять символов даты, например 2026-10-23 из строки с временем, и создаёт объект date"""
    if not isinstance(value, str):
        raise IncompleteMarketDataError(f"Cbonds не вернул {field}")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as error:
        raise IncompleteMarketDataError(f"Cbonds вернул некорректный {field}") from error


def _coupon_type(emission: dict[str, object]) -> CouponType:
    """По полю Cbonds floating_rate выбирает плавающий (1) или фиксированный (0) купон"""
    floating = emission.get("floating_rate")
    if floating in (1, "1", True):
        return CouponType.FLOATING
    if floating in (0, "0", False):
        return CouponType.FIXED
    raise IncompleteMarketDataError("Cbonds не указал тип купона")


def normalize_cbonds(
    isin: str,
    emission: dict[str, object],
    trading: dict[str, object],
    *,
    fetched_at: datetime,
) -> NormalizedBondData:
    if emission.get("isin_code") != isin or trading.get("isin_code") != isin:
        raise IncompleteMarketDataError("Cbonds вернул данные другого ISIN")
    if str(trading.get("emission_id")) != str(emission.get("id")):
        raise IncompleteMarketDataError("Cbonds вернул торги другого выпуска")

    quote_date = _date(trading.get("date"), "дату торгов")
    coupon_type = _coupon_type(emission)
    dirty_price = trading.get("dirty_price_currency")
    if dirty_price is not None and dirty_price != "":
        quote_kind = QuoteKind.AMOUNT
        quote_value = _decimal(dirty_price, "полную цену")
        price_type = PriceType.DIRTY
        accrued = None
        
    else:
        quote_kind = QuoteKind.PERCENT
        quote_value = _decimal(trading.get("avar_price"), "чистую цену")
        price_type = PriceType.CLEAN
        accrued = _decimal(trading.get("nkd"), "НКД")

    fields: dict[str, object] = {
        "isin": isin,
        "source": MarketDataSource.CBONDS,
        "currency": emission.get("currency_name"),
        "nominal_per_bond": _decimal(emission.get("outstanding_nominal_price"), "номинал"),
        "quote_kind": quote_kind,
        "quote_value": quote_value,
        "price_type": price_type,
        "quote_source": trading.get("trading_ground_name_eng") or "Cbonds trading",
        "quote_as_of_date": quote_date,
        "coupon_type": coupon_type,
        "fetched_at": fetched_at,
        "provider_instrument_id": str(emission.get("id")),
        "issue_name": emission.get("number_of_emission_eng"),
        "issuer_name": emission.get("emitent_name_eng"),
    }
    if accrued is not None:
        fields["accrued_per_bond"] = accrued
        fields["accrued_as_of_date"] = quote_date
    if coupon_type is CouponType.FIXED:
        fields["modified_duration"] = _decimal(trading.get("dur_mod"), "дюрацию")
        fields["convexity"] = _decimal(trading.get("convexity"), "выпуклость")
        fields["risk_as_of_date"] = quote_date
    else:
        frequency = emission.get("cupon_period")
        try:
            fields["coupon_frequency"] = int(frequency)
        except (TypeError, ValueError) as error:
            raise IncompleteMarketDataError("Cbonds не указал частоту купона") from error
    return NormalizedBondData.from_provider(**fields)


class CbondsAdapter:
    def __init__(
        self,
        *,
        login: str | None,
        password: str | None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        base_url: str = CBONDS_BASE_URL,
    ) -> None:
        self._login = login
        self._password = password
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._base_url = base_url.rstrip("/")

    @classmethod
    def from_settings(cls, settings: "Settings") -> "CbondsAdapter":
        return cls(
            login=settings.cbonds_login,
            password=settings.cbonds_password,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    async def get_bond(self, isin: str) -> NormalizedBondData:
        isin = validate_isin(isin)
        if not self._login or not self._password:
            raise ProviderUnavailableError("Доступ Cbonds не настроен")

        async with provider_client(self._client, self._timeout_seconds) as client:
            request: dict[str, object] = {
                "auth": {"login": self._login, "password": self._password},
                "filters": [{"field": "isin_code", "operator": "eq", "value": isin}],
                "quantity": {"limit": 100, "offset": 0},
            }
            emissions = _items(await post_json(client, f"{self._base_url}/get_emissions/", request))
            if not emissions:
                raise InstrumentNotFoundError("Cbonds не нашёл ISIN")
            emission = next((item for item in emissions if item.get("isin_code") == isin), None)
            if emission is None:
                raise IncompleteMarketDataError("Cbonds вернул выпуск другого ISIN")

            trading_request = request | {"sorting": [{"field": "date", "order": "desc"}]}
            tradings = _items(
                await post_json(client, f"{self._base_url}/get_tradings/", trading_request)
            )
            if not tradings:
                raise IncompleteMarketDataError("У Cbonds нет котировки для найденного ISIN")
            if any(item.get("isin_code") != isin for item in tradings):
                raise IncompleteMarketDataError("Cbonds вернул котировки другого ISIN")
            try:
                latest_date = max(_date(item.get("date"), "дату торгов") for item in tradings)
            except ValueError as error:
                raise IncompleteMarketDataError("Cbonds не вернул дату торгов") from error
            candidates = [
                item for item in tradings if _date(item.get("date"), "дату торгов") == latest_date
            ]
            for trading in candidates:
                try:
                    return normalize_cbonds(isin, emission, trading, fetched_at=datetime.now(UTC))
                except IncompleteMarketDataError:
                    continue
            raise IncompleteMarketDataError("У Cbonds нет полного снимка на последнюю дату торгов")
