"""Login com usuário/senha do app (PsoEducare): o DataHub não guarda a senha, só pergunta ao
PsoEducare da empresa se o par é válido (POST /servicos/integracao/v1/auth/validar-usuario)."""
import logging
import httpx
from fastapi import HTTPException

logger = logging.getLogger("datahub")

CAMINHO_VALIDAR = "/servicos/integracao/v1/auth/validar-usuario"
TIMEOUT_SEG = 8.0


async def validar_usuario_app(empresa: dict, login: str, senha: str) -> dict | None:
    """Devolve {"usuario_id": int, "nome": str} se o PsoEducare aprovar, None se reprovar.
    Falha de rede/servidor vira 503 (não é credencial inválida)."""
    url = empresa["url_impressao_base"].rstrip("/") + CAMINHO_VALIDAR
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEG) as client:
            res = await client.post(
                url,
                json={"login": login, "senha": senha},
                headers={"X-API-Key": empresa["app_login_api_key"]},
            )
        if res.status_code != 200:
            logger.error(f"login-app: PsoEducare da empresa {empresa['slug']} respondeu HTTP {res.status_code}")
            raise HTTPException(status_code=503, detail="Não foi possível validar o login agora")
        dados = res.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"login-app: falha ao chamar o PsoEducare da empresa {empresa['slug']}: {e}")
        raise HTTPException(status_code=503, detail="Não foi possível validar o login agora")

    if dados.get("valido") is not True or dados.get("usuarioId") is None:
        return None
    return {"usuario_id": dados["usuarioId"], "nome": dados.get("nome")}
