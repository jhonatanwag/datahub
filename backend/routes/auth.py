import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from config.databases import query_meta
from config.redis import get_redis
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = logging.getLogger("datahub")


class LoginInput(BaseModel):
    email: str
    senha: str


class SelecionarEmpresaInput(BaseModel):
    user_id: int
    empresa_id: int


@router.post("/login")
async def login(body: LoginInput):
    try:
        rows = await query_meta(
            "SELECT id, nome, role, senha_hash FROM usuarios WHERE email = $1 AND ativo = true",
            body.email
        )
        if not rows:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        usuario = dict(rows[0])

        if not bcrypt.checkpw(body.senha.encode(), usuario["senha_hash"].encode()):
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        empresas = await query_meta("""
            SELECT e.id, e.slug, e.nome
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
            ORDER BY e.nome
        """, usuario["id"])

        return {
            "user_id": usuario["id"],
            "nome": usuario["nome"],
            "role": usuario["role"],
            "empresas": [
                {
                    "id": e["id"],
                    "slug": e["slug"],
                    "nome": e["nome"],
                    "logo_url": f"/api/empresas/{e['id']}/logo"
                }
                for e in empresas
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no login: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.post("/selecionar-empresa")
async def selecionar_empresa(body: SelecionarEmpresaInput):
    try:
        usuario_rows = await query_meta(
            "SELECT id, nome, role FROM usuarios WHERE id = $1 AND ativo = true",
            body.user_id
        )
        if not usuario_rows:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")

        usuario = dict(usuario_rows[0])

        acesso = await query_meta("""
            SELECT e.id, e.slug FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.id = $2 AND e.ativo = true
        """, body.user_id, body.empresa_id)

        if not acesso:
            raise HTTPException(status_code=403, detail="Sem acesso a esta empresa")

        empresa = dict(acesso[0])

        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        token = jwt.encode(
            {
                "user_id": usuario["id"],
                "empresa_id": empresa["id"],
                "company_slug": empresa["slug"],
                "nome": usuario["nome"],
                "role": usuario["role"],
                "exp": expire
            },
            settings.JWT_SECRET,
            algorithm="HS256"
        )

        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao selecionar empresa: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.get("/minhas-empresas")
async def minhas_empresas(user=Depends(get_current_user)):
    try:
        empresas = await query_meta("""
            SELECT e.id, e.slug, e.nome
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
            ORDER BY e.nome
        """, user["id"])

        return [
            {
                "id": e["id"],
                "slug": e["slug"],
                "nome": e["nome"],
                "logo_url": f"/api/empresas/{e['id']}/logo"
            }
            for e in empresas
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar empresas: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


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
        logger.error(f"Erro no logout: {e}")
        raise HTTPException(status_code=500, detail="Erro no logout")
