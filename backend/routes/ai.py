from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from services.rag import build_context
from services.groq_client import ask
from services.cache import cache_get, cache_set, TTL_CHARTS
from config.databases import query_meta
import json

router = APIRouter(prefix="/api/ai", tags=["IA"])


class PerguntaInput(BaseModel):
    pergunta: str


@router.post("/ask")
async def chatbot(body: PerguntaInput, user=Depends(get_current_user)):
    try:
        ctx_key = f"rag_context:{user['company_slug']}"
        context = await cache_get(ctx_key)
        if not context:
            context = await build_context(user["company_slug"], user["empresa_id"])
            await cache_set(ctx_key, context, ttl=TTL_CHARTS)
        elif not isinstance(context, str):
            context = json.dumps(context)

        resposta = await ask(body.pergunta, context, user["company_name"])

        await query_meta(
            """INSERT INTO chat_historico (usuario_id, empresa_id, pergunta, resposta)
               VALUES ($1, $2, $3, $4)""",
            user["id"], user["empresa_id"], body.pergunta, resposta
        )

        return {"resposta": resposta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no chatbot: {e}")


@router.get("/historico")
async def historico(limit: int = 20, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            """SELECT pergunta, resposta, criado_em
               FROM chat_historico
               WHERE usuario_id = $1 AND empresa_id = $2
               ORDER BY criado_em DESC LIMIT $3""",
            user["id"], user["empresa_id"], limit
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {e}")
