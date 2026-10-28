import logging
import secrets
import json
import uuid
from typing import Literal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from config.databases import query_meta
from config.redis import get_redis
from middleware.auth import get_current_user
from services.sso import validar_empresa_sso, buscar_slugs_liberados
from services.app_login import validar_usuario_app

router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = logging.getLogger("datahub")

# Freio de força bruta do login-app: falhas por empresa+login dentro da janela
LOGIN_APP_MAX_FALHAS = 5
LOGIN_APP_JANELA_SEG = 600


class LoginInput(BaseModel):
    email: str
    senha: str


class SelecionarEmpresaInput(BaseModel):
    session_token: str
    empresa_id: int


class TemaInput(BaseModel):
    tema: Literal['claro', 'escuro']


class SsoEntrarInput(BaseModel):
    empresa_slug: str
    api_key: str
    codigo_usuario: str


class SsoMeusPaineisInput(BaseModel):
    empresa_slug: str
    api_key: str
    codigo_usuario: str


class LoginAppInput(BaseModel):
    empresa_slug: str
    login: str
    senha: str


class SsoTrocarInput(BaseModel):
    exchange: str


class PdfTokenInput(BaseModel):
    pdf_token: str


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


@router.post("/sso-entrar")
async def sso_entrar(body: SsoEntrarInput):
    try:
        empresa = await validar_empresa_sso(body.empresa_slug, body.api_key)
        slugs_liberados = await buscar_slugs_liberados(empresa, body.codigo_usuario)

        exchange_token = secrets.token_hex(32)
        redis = await get_redis()
        payload = json.dumps({
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "codigo_usuario": body.codigo_usuario,
            "paineis_liberados": slugs_liberados,
        })
        await redis.setex(f"sso_exchange:{exchange_token}", 60, payload)

        return {"redirect_url": f"{settings.FRONTEND_URL}/sso?exchange={exchange_token}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no sso-entrar: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.post("/sso-meus-paineis")
async def sso_meus_paineis(body: SsoMeusPaineisInput):
    try:
        empresa = await validar_empresa_sso(body.empresa_slug, body.api_key)
        slugs_liberados = await buscar_slugs_liberados(empresa, body.codigo_usuario)

        if not slugs_liberados:
            return []

        rows = await query_meta(
            "SELECT slug, nome, icone FROM paineis WHERE (empresa_id = $1 OR empresa_id IS NULL) AND slug = ANY($2::text[]) AND ativo = true",
            empresa["id"], slugs_liberados
        )
        return [dict(r) for r in rows]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no sso-meus-paineis: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.post("/sso/trocar")
async def sso_trocar(body: SsoTrocarInput):
    try:
        redis = await get_redis()
        raw = await redis.getdel(f"sso_exchange:{body.exchange}")
        if not raw:
            raise HTTPException(status_code=401, detail="Link inválido ou expirado")

        dados = json.loads(raw)
        return {"token": _emitir_token_externo(dados), "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao trocar token SSO: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


def _emitir_token_externo(dados: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES_EXTERNO)
    return jwt.encode(
        {
            "tipo": "externo",
            "empresa_id": dados["empresa_id"],
            "company_slug": dados["company_slug"],
            "codigo_usuario": dados["codigo_usuario"],
            "paineis_liberados": dados["paineis_liberados"],
            "jti": str(uuid.uuid4()),
            "exp": expire,
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@router.post("/login-app")
async def login_app(body: LoginAppInput):
    """Login direto no link web com o usuário/senha do app da empresa (PsoEducare). Dá o mesmo acesso
    do SSO: token externo, só com os painéis que a sso_query_acesso libera pro usuário."""
    chave_falhas = f"loginapp:falhas:{body.empresa_slug.lower()}:{body.login.lower()}"
    try:
        redis = await get_redis()
        if int(await redis.get(chave_falhas) or 0) >= LOGIN_APP_MAX_FALHAS:
            raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos.")

        rows = await query_meta(
            "SELECT id, slug, sso_query_acesso, url_impressao_base, app_login_api_key "
            "FROM empresas WHERE slug = $1 AND ativo = true",
            body.empresa_slug.strip()
        )
        empresa = dict(rows[0]) if rows else None
        # empresa inexistente ou sem login-app configurado: mesma resposta de senha errada (sem enumerar)
        if not empresa or not empresa["url_impressao_base"] or not empresa["app_login_api_key"] \
                or not empresa["sso_query_acesso"]:
            await _registrar_falha_login_app(redis, chave_falhas)
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        usuario = await validar_usuario_app(empresa, body.login.strip(), body.senha)
        if not usuario:
            await _registrar_falha_login_app(redis, chave_falhas)
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        codigo_usuario = str(usuario["usuario_id"])
        slugs_liberados = await buscar_slugs_liberados(empresa, codigo_usuario)
        if not slugs_liberados:
            raise HTTPException(status_code=403, detail="Usuário sem painéis liberados")

        await redis.delete(chave_falhas)
        token = _emitir_token_externo({
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "codigo_usuario": codigo_usuario,
            "paineis_liberados": slugs_liberados,
        })
        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no login-app: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


async def _registrar_falha_login_app(redis, chave: str) -> None:
    if await redis.incr(chave) == 1:
        await redis.expire(chave, LOGIN_APP_JANELA_SEG)


@router.post("/pdf-token/trocar")
async def trocar_pdf_token(body: PdfTokenInput):
    redis = await get_redis()
    jwt_str = await redis.getdel(f"pdf_exchange:{body.pdf_token}")
    if not jwt_str:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return {"token": jwt_str}


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


@router.post("/renovar")
async def renovar_token(user=Depends(get_current_user)):
    """Emite um token novo com os mesmos dados enquanto o atual for válido.
    Usado pela tela de apresentação (TV) pra não cair em 'sessão expirada'."""
    if user["role"] == "externo":
        raise HTTPException(status_code=403, detail="Renovação indisponível para este perfil")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "user_id": user["id"],
            "empresa_id": user["empresa_id"],
            "company_slug": user["company_slug"],
            "nome": user["nome"],
            "role": user["role"],
            "exp": expire,
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return {"token": token, "token_type": "bearer"}


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
