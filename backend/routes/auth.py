import logging
import secrets
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from config.databases import query_meta, query_company
from config.redis import get_redis
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = logging.getLogger("datahub")


class LoginInput(BaseModel):
    email: str
    senha: str


class SelecionarEmpresaInput(BaseModel):
    session_token: str
    empresa_id: int


class TemaInput(BaseModel):
    tema: Literal['claro', 'escuro']


class SsoPainelInput(BaseModel):
    empresa_slug: str
    api_key: str
    codigo_usuario: str
    painel_slug: str


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

        session_token = secrets.token_hex(32)
        redis = await get_redis()
        await redis.setex(f"session:{session_token}", 300, str(usuario["id"]))

        return {
            "user_id": usuario["id"],
            "nome": usuario["nome"],
            "role": usuario["role"],
            "session_token": session_token,
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
        redis = await get_redis()
        user_id_str = await redis.getdel(f"session:{body.session_token}")
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")

        user_id = int(user_id_str)

        usuario_rows = await query_meta(
            "SELECT id, nome, role FROM usuarios WHERE id = $1 AND ativo = true",
            user_id
        )
        if not usuario_rows:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")

        usuario = dict(usuario_rows[0])

        acesso = await query_meta("""
            SELECT e.id, e.slug FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.id = $2 AND e.ativo = true
        """, user_id, body.empresa_id)

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

        await redis.delete(f"blacklist:{user_id}")
        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao selecionar empresa: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.post("/sso-painel")
async def sso_painel(body: SsoPainelInput):
    try:
        empresa_rows = await query_meta(
            "SELECT id, slug, sso_api_key_hash FROM empresas WHERE slug = $1 AND ativo = true",
            body.empresa_slug
        )
        if not empresa_rows:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        empresa = dict(empresa_rows[0])

        if not empresa["sso_api_key_hash"]:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        if not bcrypt.checkpw(body.api_key.encode(), empresa["sso_api_key_hash"].encode()):
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        painel_rows = await query_meta(
            "SELECT id, slug FROM paineis WHERE slug = $1 AND empresa_id = $2 AND ativo = true",
            body.painel_slug, empresa["id"]
        )
        if not painel_rows:
            raise HTTPException(status_code=404, detail="Painel não encontrado")

        try:
            acesso_rows = await query_company(
                empresa["slug"],
                """
                SELECT EXISTS (
                    SELECT 1 FROM vw_datahub_sso_acesso
                    WHERE codigo_usuario = $1 AND painel_slug = $2
                ) AS tem_acesso
                """,
                body.codigo_usuario, body.painel_slug
            )
        except Exception as e:
            logger.error(f"Erro ao verificar acesso SSO: {e}")
            raise HTTPException(status_code=500, detail="Erro interno no servidor")

        if not acesso_rows[0]["tem_acesso"]:
            raise HTTPException(status_code=403, detail="Sem acesso a este painel")

        exchange_token = secrets.token_hex(32)
        redis = await get_redis()
        payload = json.dumps({
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "codigo_usuario": body.codigo_usuario,
            "painel_slug": body.painel_slug,
        })
        await redis.setex(f"sso_exchange:{exchange_token}", 60, payload)

        return {"redirect_url": f"{settings.FRONTEND_URL}/sso?exchange={exchange_token}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no sso-painel: {e}")
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar empresas: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.put("/tema")
async def atualizar_tema(body: TemaInput, user=Depends(get_current_user)):
    try:
        await query_meta("UPDATE usuarios SET tema = $1 WHERE id = $2", body.tema, user["id"])
        return {"tema": body.tema}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar tema: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    try:
        redis = await get_redis()
        await redis.setex(f"blacklist:{user['id']}", settings.JWT_EXPIRE_MINUTES * 60, "1")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro no logout: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")
