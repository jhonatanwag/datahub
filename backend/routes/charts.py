from fastapi import APIRouter, Depends, Query as QueryParam
from typing import Optional
from middleware.auth import get_current_user
from services.query_runner import resolver_query
from fastapi import HTTPException

router = APIRouter(prefix="/api/charts", tags=["Charts"])


@router.get("/{slug}")
async def executar_chart(
    slug: str,
    data_inicio: Optional[str] = QueryParam(None),
    data_fim: Optional[str] = QueryParam(None),
    user=Depends(get_current_user)
):
    parametros = {}
    if data_inicio:
        parametros["data_inicio"] = data_inicio
    if data_fim:
        parametros["data_fim"] = data_fim

    try:
        return await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"],
            parametros=parametros
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar chart: {e}")
