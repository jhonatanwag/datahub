from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from config.databases import query_meta
import json
import uuid

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class SolicitarInput(BaseModel):
    tipo: str = "relatorio_mensal"


@router.post("/solicitar")
async def solicitar_relatorio(body: SolicitarInput, user=Depends(get_current_user)):
    try:
        rows = await query_meta("""
            INSERT INTO tarefas (tipo, empresa_id, usuario_id, status, payload)
            VALUES ($1, $2, $3, 'pendente', $4::jsonb)
            RETURNING id
        """, body.tipo, user["empresa_id"], user["id"],
            json.dumps({"company_slug": user["company_slug"]})
        )
        tarefa_id = str(rows[0]["id"])
        return {"tarefa_id": tarefa_id, "status": "pendente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao solicitar relatório: {e}")


@router.get("/status/{tarefa_id}")
async def status_relatorio(tarefa_id: str, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT id, status, criado_em, concluido_em FROM tarefas WHERE id = $1 AND empresa_id = $2",
            uuid.UUID(tarefa_id), user["empresa_id"]
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        return dict(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar status: {e}")


@router.get("/resultado/{tarefa_id}")
async def resultado_relatorio(tarefa_id: str, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT id, status, resultado FROM tarefas WHERE id = $1 AND empresa_id = $2",
            uuid.UUID(tarefa_id), user["empresa_id"]
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        row = dict(rows[0])
        if row["status"] != "ok":
            return {"status": row["status"], "resultado": None}
        return {"status": row["status"], "resultado": row["resultado"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar resultado: {e}")
