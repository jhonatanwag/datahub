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

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    redis = await get_redis()
    if await redis.get(f"blacklist:{user_id}"):
        raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

    rows = await query_meta("""
        SELECT u.id, u.nome, u.role,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name
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
