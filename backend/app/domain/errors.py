class DomainError(Exception):
    """Ошибка, которую сервис может преобразовать в понятный ответ API"""


class InvalidISINError(DomainError):
    """ISIN не соответствует формату или контрольной цифре"""


class InvalidQuantityError(DomainError):
    """Количество облигаций не является допустимым целым числом"""


class MarketDataError(DomainError):
    """Не удалось получить пригодные рыночные данные"""


class InstrumentNotFoundError(MarketDataError):
    """Поставщик не знает указанный ISIN"""


class ProviderUnavailableError(MarketDataError):
    """Поставщик не ответил или вернул техническую ошибку"""


class IncompleteMarketDataError(MarketDataError):
    """В ответе нет обязательного для расчёта параметра"""


class StaleMarketDataError(MarketDataError):
    """Данные не удовлетворяют принятому правилу свежести"""


class FXRateUnavailableError(DomainError):
    """Не найден действующий курс валюты на дату расчёта"""
