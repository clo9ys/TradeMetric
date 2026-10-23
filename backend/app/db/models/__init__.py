# Импорт всех моделей регистрирует таблицы в Base.metadata: на него смотрит Alembic.
from app.db.models.auth_session import AuthSession
from app.db.models.calculation import Calculation
from app.db.models.calculation_trade import CalculationTrade
from app.db.models.instrument_snapshot import InstrumentSnapshot
from app.db.models.user import User

__all__ = ["AuthSession", "Calculation", "CalculationTrade", "InstrumentSnapshot", "User"]
