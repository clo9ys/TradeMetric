from enum import Enum


class CouponType(str, Enum):
    FIXED = "fixed"
    FLOATING = "floating"


class PriceType(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"


class QuoteKind(str, Enum):
    PERCENT = "percent"
    AMOUNT = "amount"


class MarketDataSource(str, Enum):
    CBONDS = "cbonds"
    RUDATA = "rudata"
