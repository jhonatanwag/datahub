from fastapi import APIRouter, Depends, Query as QueryParam, HTTPException
from typing import Optional
from middleware.auth import get_current_user
from config.databases import query_company

router = APIRouter(prefix="/api/tables", tags=["Tables"])


@router.get("/pedidos")
async def listar_pedidos(
    page: int = QueryParam(1, ge=1),
    limit: int = QueryParam(20, ge=1, le=100),
    status: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    user=Depends(get_current_user)
):
    try:
        filtros = ["1=1"]
        params: list = []

        if status:
            params.append(status)
            filtros.append(f"status = ${len(params)}")
        if data_inicio:
            params.append(data_inicio)
            filtros.append(f"data >= ${len(params)}::timestamp")
        if data_fim:
            params.append(data_fim)
            filtros.append(f"data <= ${len(params)}::timestamp")

        where = " AND ".join(filtros)

        count_rows = await query_company(
            user["company_slug"],
            f"SELECT COUNT(*) AS total FROM pedidos WHERE {where}",
            *params
        )
        total = count_rows[0]["total"]
        pages = (total + limit - 1) // limit

        offset = (page - 1) * limit
        params_page = params + [limit, offset]
        n = len(params)

        rows = await query_company(
            user["company_slug"],
            f"""SELECT id, cliente_nome, produto, valor, status, canal,
                       TO_CHAR(data, 'DD/MM/YYYY HH24:MI') AS data
                FROM pedidos WHERE {where}
                ORDER BY data DESC
                LIMIT ${n+1} OFFSET ${n+2}""",
            *params_page
        )

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar pedidos: {e}")
