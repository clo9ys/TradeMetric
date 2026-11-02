from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import IncompleteMarketDataError, StaleMarketDataError
from app.domain.market_data import NormalizedBondData


@pytest.fixture
def fixed_fields():
    return {
        "isin": "RU000A10D4Y2",
        "source": MarketDataSource.CBONDS,
        "currency": "RUB",
        "nominal_per_bond": Decimal("1000"),
        "quote_kind": QuoteKind.PERCENT,
        "quote_value": Decimal("86.192"),
        "price_type": PriceType.DIRTY,
        "quote_source": "MOEX TQOB via Cbonds",
        "quote_as_of_date": date(2026, 10, 23),
        "coupon_type": CouponType.FIXED,
        "fetched_at": datetime(2026, 10, 25, 12, tzinfo=timezone.utc),
        "modified_duration": Decimal("4.5"),
        "convexity": Decimal("25.0"),
        "risk_as_of_date": date(2026, 10, 23),
    }


def test_complete_fixed_bond_preserves_dates_and_decimals(fixed_fields):
    bond = NormalizedBondData.from_provider(**fixed_fields)

    assert bond.isin == "RU000A10D4Y2"
    assert bond.quote_value == Decimal("86.192")
    assert bond.quote_as_of_date == date(2026, 10, 23)
    assert bond.risk_as_of_date == date(2026, 10, 23)
    assert bond.accrued_as_of_date is None
    bond.validate_freshness(
        calculation_date=date(2026, 10, 25), last_trading_date=date(2026, 10, 23)
    )


def test_clean_price_requires_accrued_and_its_date(fixed_fields):
    fixed_fields["price_type"] = PriceType.CLEAN

    with pytest.raises(IncompleteMarketDataError, match="НКД"):
        NormalizedBondData.from_provider(**fixed_fields)

    fixed_fields["accrued_per_bond"] = Decimal("1.71")
    fixed_fields["accrued_as_of_date"] = date(2026, 10, 25)
    bond = NormalizedBondData.from_provider(**fixed_fields)
    assert bond.accrued_per_bond == Decimal("1.71")


def test_dirty_price_does_not_require_accrued(fixed_fields):
    assert NormalizedBondData.from_provider(**fixed_fields).accrued_per_bond is None


def test_floating_coupon_requires_frequency_not_risk_metrics(fixed_fields):
    fixed_fields["coupon_type"] = CouponType.FLOATING
    fixed_fields["coupon_frequency"] = 4
    fixed_fields.pop("modified_duration")
    fixed_fields.pop("convexity")
    fixed_fields.pop("risk_as_of_date")

    bond = NormalizedBondData.from_provider(**fixed_fields)
    assert bond.coupon_frequency == 4
    bond.validate_freshness(
        calculation_date=date(2026, 10, 25), last_trading_date=date(2026, 10, 23)
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"modified_duration": None}, "риск-параметры"),
        ({"convexity": None}, "риск-параметры"),
        ({"risk_as_of_date": None}, "риск-параметры"),
        ({"nominal_per_bond": None}, "nominal_per_bond"),
        ({"quote_value": Decimal("0")}, "quote_value"),
        ({"quote_value": 86.192}, "Decimal"),
        ({"accrued_per_bond": Decimal("-1")}, "НКД"),
        ({"coupon_frequency": 0}, "Частота"),
        ({"currency": "rub"}, "Валюта"),
        ({"source": "cbonds"}, "источник"),
        ({"isin": "RU000A10D4Y3"}, "ISIN"),
        ({"fetched_at": datetime(2026, 10, 25, 12)}, "часовой пояс"),
    ],
)
def test_invalid_provider_data_is_rejected(fixed_fields, changes, message):
    with pytest.raises(IncompleteMarketDataError, match=message):
        NormalizedBondData.from_provider(**(fixed_fields | changes))


def test_missing_required_field_is_incomplete_provider_data(fixed_fields):
    fixed_fields.pop("quote_value")

    with pytest.raises(IncompleteMarketDataError):
        NormalizedBondData.from_provider(**fixed_fields)


def test_floating_coupon_without_frequency_is_incomplete(fixed_fields):
    fixed_fields["coupon_type"] = CouponType.FLOATING

    with pytest.raises(IncompleteMarketDataError, match="частота"):
        NormalizedBondData.from_provider(**fixed_fields)


def test_quote_and_risk_must_be_from_last_trading_day(fixed_fields):
    stale_quote = NormalizedBondData.from_provider(
        **(fixed_fields | {"quote_as_of_date": date(2026, 10, 22)})
    )
    with pytest.raises(StaleMarketDataError, match="Котировка"):
        stale_quote.validate_freshness(
            calculation_date=date(2026, 10, 25), last_trading_date=date(2026, 10, 23)
        )

    stale_risk = NormalizedBondData.from_provider(
        **(fixed_fields | {"risk_as_of_date": date(2026, 10, 22)})
    )
    with pytest.raises(StaleMarketDataError, match="Риск-параметры"):
        stale_risk.validate_freshness(
            calculation_date=date(2026, 10, 25), last_trading_date=date(2026, 10, 23)
        )


def test_accrued_date_cannot_be_after_calculation(fixed_fields):
    bond = NormalizedBondData.from_provider(
        **(
            fixed_fields
            | {
                "price_type": PriceType.CLEAN,
                "accrued_per_bond": Decimal("1.71"),
                "accrued_as_of_date": date(2026, 10, 26),
            }
        )
    )

    with pytest.raises(StaleMarketDataError, match="Дата НКД"):
        bond.validate_freshness(
            calculation_date=date(2026, 10, 25), last_trading_date=date(2026, 10, 23)
        )
