from fastapi import APIRouter

from app.api.deps import CurrentSession
from app.config import get_settings
from app.providers.csv import CsvBondDataProvider
from app.providers.factory import build_bond_provider

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("")
async def instruments(_: CurrentSession) -> dict[str, object]:
    provider, source = build_bond_provider(get_settings())
    bonds = await provider.list_bonds() if isinstance(provider, CsvBondDataProvider) else ()
    return {
        "source": source.value,
        "catalog_available": isinstance(provider, CsvBondDataProvider),
        "instruments": [
            {
                "isin": bond.isin,
                "issue_name": bond.issue_name,
                "issuer_name": bond.issuer_name,
                "currency": bond.currency,
                "coupon_type": bond.coupon_type.value,
                "quote_as_of_date": bond.quote_as_of_date.isoformat(),
                "default_quantity": 1,
            }
            for bond in bonds
        ],
    }
