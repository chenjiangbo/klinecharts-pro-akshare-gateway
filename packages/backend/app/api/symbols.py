from fastapi import APIRouter, Query, Request

from app.models import SymbolSearchResponse

router = APIRouter()


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols(
    request: Request,
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=50),
):
    if not q:
        return SymbolSearchResponse(items=[])
    provider = request.app.state.async_provider
    items = await provider.search_symbols(q, limit)
    return SymbolSearchResponse(items=items)
