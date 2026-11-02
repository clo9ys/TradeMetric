from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import FXRateUnavailableError, InvalidQuantityError
from app.domain.market_data import NormalizedBondData
from app.services.calculation import calculate_total_dv01, calculate_trade_metrics


@pytest.fixture
def fixed_bond() -> NormalizedBondData:
    return NormalizedBondData(
        isin="RU000A10D4Y2",
        source=MarketDataSource.CBONDS,
        currency="RUB",
        nominal_per_bond=Decimal("1000"),
        quote_kind=QuoteKind.PERCENT,
        quote_value=Decimal("101.25"),
        price_type=PriceType.CLEAN,
        quote_source="synthetic unit test",
        quote_as_of_date=date(2026, 10, 23),
        coupon_type=CouponType.FIXED,
        fetched_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
        accrued_per_bond=Decimal("12.3"),
        accrued_as_of_date=date(2026, 10, 23),
        modified_duration=Decimal("4.2"),
        convexity=Decimal("19.5"),
        risk_as_of_date=date(2026, 10, 23),
    )


def test_clean_fixed_price_and_signed_quantity(fixed_bond: NormalizedBondData):
    buy = calculate_trade_metrics(fixed_bond, 3, Decimal("1"))
    short = calculate_trade_metrics(fixed_bond, -1, Decimal("1"))

    assert buy.dirty_price_per_bond == Decimal("1024.8")
    assert buy.current_fair_value_rub == Decimal("3074.4")
    assert buy.duration_used == Decimal("4.2")
    assert buy.convexity_used == Decimal("19.5")
    assert buy.dv01_rub == buy.current_fair_value_rub * (
        -Decimal("4.2") * Decimal("0.0001")
        + Decimal("0.5") * Decimal("19.5") * Decimal("0.0001") ** 2
    )
    assert short.current_fair_value_rub == Decimal("-1024.8")
    assert short.dv01_rub == -buy.dv01_rub / 3


def test_dirty_price_does_not_add_accrued_again_and_uses_fx(fixed_bond: NormalizedBondData):
    dirty_bond = replace(
        fixed_bond,
        currency="USD",
        quote_kind=QuoteKind.AMOUNT,
        quote_value=Decimal("1043.125"),
        price_type=PriceType.DIRTY,
        accrued_per_bond=Decimal("23.4"),
    )

    result = calculate_trade_metrics(dirty_bond, -2, Decimal("80.5"))

    assert result.dirty_price_per_bond == Decimal("1043.125")
    assert result.current_fair_value_rub == Decimal("-167943.125")


def test_floating_duration_and_portfolio_sum(fixed_bond: NormalizedBondData):
    floating_bond = replace(
        fixed_bond,
        coupon_type=CouponType.FLOATING,
        coupon_frequency=4,
        quote_kind=QuoteKind.AMOUNT,
        quote_value=Decimal("997.75"),
        accrued_per_bond=Decimal("1.25"),
        modified_duration=None,
        convexity=None,
        risk_as_of_date=None,
    )
    first = calculate_trade_metrics(fixed_bond, 3, Decimal("1"))
    second = calculate_trade_metrics(fixed_bond, -1, Decimal("1"))
    third = calculate_trade_metrics(floating_bond, 4, Decimal("1"))

    assert third.dirty_price_per_bond == Decimal("999")
    assert third.duration_used == Decimal("0.25")
    assert third.convexity_used == Decimal("0")
    assert third.current_fair_value_rub == Decimal("3996")
    assert calculate_total_dv01([first, second, third]) == (
        first.dv01_rub + second.dv01_rub + third.dv01_rub
    )
    assert calculate_total_dv01([]) == Decimal(0)


@pytest.mark.parametrize("quantity", [0, True, 1.5])
def test_invalid_quantity_is_rejected(fixed_bond: NormalizedBondData, quantity: object):
    with pytest.raises(InvalidQuantityError):
        calculate_trade_metrics(fixed_bond, quantity, Decimal("1"))


@pytest.mark.parametrize("fx_rate", [Decimal("0"), Decimal("NaN"), 1.0, Decimal("2")])
def test_invalid_rub_fx_is_rejected(fixed_bond: NormalizedBondData, fx_rate: object):
    with pytest.raises(FXRateUnavailableError):
        calculate_trade_metrics(fixed_bond, 1, fx_rate)
