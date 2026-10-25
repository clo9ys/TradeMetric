from enum import Enum


class CouponType(str, Enum):
    """Тип купона облигации"""
    FIXED = "fixed"
    FLOATING = "floating"


class PriceType(str, Enum):
    """Показывает, включён ли НКД в котировку"""
    CLEAN = "clean"
    DIRTY = "dirty"


class QuoteKind(str, Enum):
    """Единица измерения котировки: процент номинала или сумма"""
    PERCENT = "percent"
    AMOUNT = "amount"


class MarketDataSource(str, Enum):
    """Поставщик рыночного снимка"""
    CBONDS = "cbonds"
    RUDATA = "rudata"
