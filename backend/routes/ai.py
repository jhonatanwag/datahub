from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from middleware.auth import get_current_user
from services.rag import listar_ferramentas_rag, executar_ferramenta_rag
from services.groq_client import ask, transcrever, LimiteTokensError
from config.databases import query_meta

router = APIRouter(prefix="/api/ai", tags=["IA"])


class PerguntaInput(BaseModel):
    pergunta: str


@router.post("/ask")
async def chatbot(body: PerguntaInput, user=Depends(get_current_user)):
    try:
        ferramentas = await listar_ferramentas_rag(user["empresa_id"])

        async def executar_ferramenta(nome: str) -> str:
            return await executar_ferramenta_rag(nome, user["company_slug"], user["empresa_id"])

        resultado = await ask(body.pergunta, ferramentas, executar_ferramenta, user["company_name"])

        await query_meta(
            """INSERT INTO chat_historico (usuario_id, empresa_id, pergunta, resposta)
               VALUES ($1, $2, $3, $4)""",
            user["id"], user["empresa_id"], body.pergunta, resultado["resposta"]
        )

        return resultado
    except LimiteTokensError as e:
        raise HTTPException(
            status_code=429,
            detail={"erro": "limite_tokens", "espere_segundos": e.espere_segundos},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no chatbot: {e}")


@router.post("/transcrever")
async def transcrever_audio(file: UploadFile = File(...), user=Depends(get_current_user)):
    try:
        audio_bytes = await file.read()
        texto = await transcrever(audio_bytes, file.filename or "audio.webm")
        return {"texto": texto}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao transcrever áudio: {e}")


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
