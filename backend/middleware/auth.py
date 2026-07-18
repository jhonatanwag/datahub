from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from config.settings import settings
from config.databases import query_meta
from config.redis import get_redis

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    empresa_id = payload.get("empresa_id")
    if empresa_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    redis = await get_redis()

    if payload.get("tipo") == "externo":
        jti = payload.get("jti")
        codigo_usuario = payload.get("codigo_usuario")
        paineis_liberados = payload.get("paineis_liberados")
        if not jti or not codigo_usuario or paineis_liberados is None:
            raise HTTPException(status_code=401, detail="Token inválido")

        if await redis.get(f"blacklist:externo:{jti}"):
            raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

        empresa_rows = await query_meta(
            "SELECT id, nome, slug FROM empresas WHERE id = $1 AND ativo = true",
            empresa_id
        )
        if not empresa_rows:
            raise HTTPException(status_code=403, detail="Acesso negado")
        empresa = dict(empresa_rows[0])

        return {
            "id": None,
            "nome": None,
            "role": "externo",
            "tema": None,
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "company_name": empresa["nome"],
            "codigo_usuario": codigo_usuario,
            "paineis_liberados": paineis_liberados,
        }

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    if await redis.get(f"blacklist:{user_id}"):
        raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

    rows = await query_meta("""
        SELECT u.id, u.nome, u.role, u.tema,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name,
               ue.codigo_usuario_externo
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, user_id, empresa_id)

    if not rows:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return dict(rows[0])


async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Requer perfil admin")
    return user
