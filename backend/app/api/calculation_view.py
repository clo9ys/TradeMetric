from decimal import Decimal

from app.db.models import Calculation


def calculation_view(calculation: Calculation) -> dict[str, object]:
    """Представление сохранённого расчёта для таблицы и истории сайта"""
    sources = {trade.snapshot.source for trade in calculation.trades}
    return {
        "calculation_id": str(calculation.id),
        "calculated_at": calculation.calculated_at.isoformat(),
        "source": next(iter(sources)) if len(sources) == 1 else "mixed",
        "currency": "RUB",
        "total_dv01_rub": str(sum((trade.dv01 for trade in calculation.trades), Decimal(0))),
        "total_fair_value_rub": str(
            sum((trade.current_fair_value for trade in calculation.trades), Decimal(0))
        ),
        "trades": [
            {
                "isin": trade.snapshot.isin,
                "issue_name": trade.snapshot.issue_name,
                "issuer_name": trade.snapshot.issuer_name,
                "currency": trade.snapshot.currency,
                "coupon_type": trade.snapshot.coupon_type,
                "market_data_source": trade.snapshot.source,
                "quantity": trade.quantity,
                "fair_value_rub": str(trade.current_fair_value),
                "dv01_rub": str(trade.dv01),
                "fx_rate_rub": str(trade.fx_rate_rub) if trade.fx_rate_rub is not None else None,
                "fx_source": trade.fx_source,
                "fx_effective_date": str(trade.fx_effective_date)
                if trade.fx_effective_date
                else None,
                "fx_fetched_at": trade.fx_snapshot.fetched_at.isoformat()
                if trade.fx_snapshot
                else None,
            }
            for trade in calculation.trades
        ],
    }
