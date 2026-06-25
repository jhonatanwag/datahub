from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
import bcrypt
from config.settings import settings
from config.databases import query_meta
from config.redis import get_redis
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginInput(BaseModel):
    email: str
    senha: str
    company_slug: str


@router.post("/login")
async def login(body: LoginInput):
    try:
        rows = await query_meta(
            "SELECT * FROM usuarios WHERE email = $1 AND ativo = true",
            body.email
        )
        if not rows:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        usuario = dict(rows[0])

        if not bcrypt.checkpw(body.senha.encode(), usuario["senha_hash"].encode()):
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Verifica acesso à empresa
        acesso = await query_meta("""
            SELECT e.id FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.slug = $2 AND e.ativo = true
        """, usuario["id"], body.company_slug)

        if not acesso:
            raise HTTPException(status_code=403, detail="Sem acesso a esta empresa")

        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        token = jwt.encode(
            {"user_id": usuario["id"], "company_slug": body.company_slug, "exp": expire},
            settings.JWT_SECRET,
            algorithm="HS256"
        )

        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no login: {e}")


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    try:
        redis = await get_redis()
        await redis.setex(f"blacklist:{user['id']}", settings.JWT_EXPIRE_MINUTES * 60, "1")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no logout: {e}")
