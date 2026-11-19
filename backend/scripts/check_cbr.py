import argparse
import asyncio
from datetime import date, datetime

from app.config import get_settings
from app.providers.cbr import CBRRateAdapter
from app.services.market_data import MOSCOW


async def check(currency: str, calculation_date: date) -> None:
    rate = await CBRRateAdapter.from_settings(get_settings()).get_rate(currency, calculation_date)
    print(
        f"currency={rate.currency}; rub_per_unit={rate.rub_per_unit}; "
        f"requested_date={calculation_date}; effective_date={rate.effective_date}; "
        f"fetched_at={rate.fetched_at.isoformat()}; source={rate.source}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Реальный запрос к Банку России, без записи в БД")
    parser.add_argument("currency", help="Код валюты, например USD или CNY")
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(MOSCOW).date())
    args = parser.parse_args()
    asyncio.run(check(args.currency, args.date))
