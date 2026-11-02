import pytest

from app.domain.enums import CouponType, MarketDataSource, PriceType, QuoteKind
from app.domain.errors import (
    FXRateUnavailableError,
    IncompleteMarketDataError,
    InstrumentNotFoundError,
    InvalidISINError,
    InvalidQuantityError,
    MarketDataError,
    ProviderUnavailableError,
    StaleMarketDataError,
)
from app.domain.isin import validate_isin
from app.domain.position import MAX_QUANTITY, MIN_QUANTITY, validate_quantity


@pytest.mark.parametrize("isin", ["RU000A10D4Y2", "XS0157815647"])
def test_valid_isin(isin):
    assert validate_isin(isin) == isin


def test_isin_is_normalized():
    assert validate_isin(" ru000a10d4y2 ") == "RU000A10D4Y2"


@pytest.mark.parametrize(
    "isin",
    ["RU000A10D4Y3", "RU000A10D4Y", "RU000A10D4Y22", "R!000A10D4Y2", "", None],
)
def test_invalid_isin(isin):
    with pytest.raises(InvalidISINError):
        validate_isin(isin)


@pytest.mark.parametrize("quantity", [1, -1, MIN_QUANTITY, MAX_QUANTITY])
def test_valid_quantity(quantity):
    assert validate_quantity(quantity) == quantity


@pytest.mark.parametrize("quantity", [0, True, 1.0, "1", MIN_QUANTITY - 1, MAX_QUANTITY + 1])
def test_invalid_quantity(quantity):
    with pytest.raises(InvalidQuantityError):
        validate_quantity(quantity)


def test_market_data_errors_are_distinct():
    error_types = {
        InstrumentNotFoundError,
        ProviderUnavailableError,
        IncompleteMarketDataError,
        StaleMarketDataError,
    }
    assert len(error_types) == 4
    assert all(issubclass(error_type, MarketDataError) for error_type in error_types)
    assert not issubclass(FXRateUnavailableError, MarketDataError)


def test_domain_enums_match_database_values():
    assert CouponType.FLOATING.value == "floating"
    assert PriceType.DIRTY.value == "dirty"
    assert QuoteKind.PERCENT.value == "percent"
    assert MarketDataSource.CBONDS.value == "cbonds"
