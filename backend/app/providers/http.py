from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.domain.errors import IncompleteMarketDataError, ProviderUnavailableError


@asynccontextmanager
async def provider_client( client: httpx.AsyncClient | None, timeout_seconds: float) -> AsyncIterator[httpx.AsyncClient]:
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(timeout=timeout_seconds) as new_client:
            yield new_client


async def post_json(
    client: httpx.AsyncClient, url: str, payload: dict[str, object], *, headers: dict[str, str] | None = None,
) -> object:
    try:
        response = await client.post(url, json=payload, headers=headers)
    except (httpx.TimeoutException, httpx.RequestError) as error:
        raise ProviderUnavailableError("Поставщик рыночных данных недоступен") from error

    if not 200 <= response.status_code < 300:
        raise ProviderUnavailableError(
            f"Поставщик рыночных данных вернул HTTP {response.status_code}"
        )
    try:
        return response.json(parse_float=str)
    except (ValueError, TypeError) as error:
        raise IncompleteMarketDataError("Поставщик вернул некорректный JSON") from error
