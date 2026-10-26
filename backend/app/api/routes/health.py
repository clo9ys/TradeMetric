from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    flag = await request.app.state.db.ping()
    if flag:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "database": "ok"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "error", "database": "unavailable"},
    )
