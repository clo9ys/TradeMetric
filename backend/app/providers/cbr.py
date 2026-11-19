from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from xml.etree import ElementTree

import httpx

from app.domain.errors import FXRateUnavailableError
from app.domain.market_data import CURRENCY_PATTERN
from app.providers.fx import FXRate
from app.providers.http import provider_client

if TYPE_CHECKING:
    from app.config import Settings

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


class CBRRateAdapter:
    """Получает официальный курс валюты из XML-сервиса Банка России"""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        url: str = CBR_DAILY_URL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:

        self._timeout_seconds = timeout_seconds
        self._client = client
        self._url = url
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, settings: "Settings") -> "CBRRateAdapter":
        """Создаёт адаптер с таймаутом из настроек"""
        return cls(timeout_seconds=settings.provider_timeout_seconds)

    async def get_rate(self, currency: str, calculation_date: date) -> FXRate:
        """Возвращает курс за одну единицу валюты, действующий на дату расчёта"""
        if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
            raise FXRateUnavailableError("Валюта должна быть кодом ISO 4217")
        if type(calculation_date) is not date:
            raise FXRateUnavailableError("Не указана дата расчёта курса")
        if currency == "RUB":
            return FXRate(Decimal(1), calculation_date, "RUB", currency, self._clock())

        try:
            async with provider_client(self._client, self._timeout_seconds) as client:
                response = await client.get(
                    self._url,
                    params={"date_req": calculation_date.strftime("%d/%m/%Y")},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise FXRateUnavailableError("Банк России не ответил на запрос курса") from error

        try:
            # данные из XML превращаем в структуру, по которой можно искать данные
            root = ElementTree.fromstring(response.content)
            if root.tag != "ValCurs":
                raise ValueError("Некорректный документ курсов")
            effective_date = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
            if effective_date > calculation_date:
                raise ValueError("Курс начал действовать позже даты расчёта")
            for item in root.findall("Valute"):
                if item.findtext("CharCode") != currency:
                    continue
                nominal = Decimal(item.findtext("Nominal", "").replace(",", "."))
                value = Decimal(item.findtext("Value", "").replace(",", "."))
                if (
                    not nominal.is_finite()
                    or nominal <= 0
                    or nominal != nominal.to_integral_value()
                    or not value.is_finite()
                    or value <= 0
                ):
                    raise ValueError("Некорректные Value или Nominal")
                rate = value / nominal
                if not rate.is_finite() or rate <= 0:
                    raise ValueError("Некорректный курс")
                result = FXRate(rate, effective_date, "CBR", currency, self._clock())
                result.validate_for(currency, calculation_date)
                return result
        except (
            ElementTree.ParseError,
            KeyError,
            ValueError,
            InvalidOperation,
            ZeroDivisionError,
        ) as error:
            raise FXRateUnavailableError("Банк России вернул некорректный курс") from error
        raise FXRateUnavailableError(f"Банк России не опубликовал курс {currency}")
