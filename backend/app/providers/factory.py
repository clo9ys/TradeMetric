from collections.abc import Callable
from datetime import datetime

from app.config import Settings
from app.domain.enums import MarketDataSource
from app.providers.base import BondDataProvider
from app.providers.cbonds import CbondsAdapter
from app.providers.csv import CsvBondDataProvider


def build_bond_provider(
    settings: Settings,
    *,
    clock: Callable[[], datetime] | None = None,
) -> tuple[BondDataProvider, MarketDataSource]:
    """Явный выбор одного источника без fallback."""
    if settings.bond_data_source == "cbonds":
        return CbondsAdapter.from_settings(settings), MarketDataSource.CBONDS
    source = MarketDataSource.DEMO if settings.csv_data_mode == "demo" else MarketDataSource.CSV
    return CsvBondDataProvider(
        settings.resolved_csv_path,
        source=source,
        clock=clock,
        require_manifest=settings.csv_require_manifest,
    ), source
