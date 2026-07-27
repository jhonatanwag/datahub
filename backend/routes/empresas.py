import os
import asyncpg
import aiofiles
import aiofiles.os
import bcrypt
import secrets
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from config.databases import query_meta, query_company
from middleware.auth import require_admin
from services.sso import validar_coluna_painel_slug
from services.query_runner import validar_sql

router = APIRouter(prefix="/api/empresas", tags=["Empresas"])

LOGOS_DIR = "/data/logos"
os.makedirs(LOGOS_DIR, exist_ok=True)


class EmpresaInput(BaseModel):
    slug: str
    nome: str
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_pass: str
    ativo: bool = True
    url_impressao_base: str | None = None


class EmpresaUpdate(BaseModel):
    slug: str
    nome: str
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_pass: str | None = None  # None = keep existing
    ativo: bool = True
    sso_query_acesso: str | None = None
    url_impressao_base: str | None = None


class TestarConexaoInput(BaseModel):
    host: str
    port: int
    database: str
    user: str
    password: str


class TestarSsoAcessoInput(BaseModel):
    empresa_id: int
    query: str
    codigo_usuario: str


@router.get("/")
async def listar_empresas(user=Depends(require_admin)):
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, ativo, criado_em FROM empresas ORDER BY nome"
    )
    return [
        {**dict(r), "logo_url": f"/api/empresas/{r['id']}/logo"}
        for r in rows
    ]


@router.post("/testar-conexao")
async def testar_conexao(body: TestarConexaoInput, user=Depends(require_admin)):
    try:
        conn = await asyncpg.connect(
            host=body.host,
            port=body.port,
            database=body.database,
            user=body.user,
            password=body.password,
            timeout=5
        )
        try:
            result = await conn.fetchrow(
                "SELECT COUNT(*)::int AS n FROM information_schema.tables WHERE table_schema = 'public'"
            )
        finally:
            await conn.close()
        return {"ok": True, "tabelas": result["n"]}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.get("/{id}")
async def buscar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, db_user, ativo, criado_em, sso_query_acesso, url_impressao_base FROM empresas WHERE id = $1",
        id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    row = dict(rows[0])
    row["logo_url"] = f"/api/empresas/{id}/logo"
    return row


@router.post("/")
async def criar_empresa(body: EmpresaInput, user=Depends(require_admin)):
    try:
        conn = await asyncpg.connect(
            host=body.db_host, port=body.db_port, database=body.db_name,
            user=body.db_user, password=body.db_pass, timeout=5
        )
        try:
            pass
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Conexão com o banco falhou: {e}")

    try:
        rows = await query_meta("""
            INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo, url_impressao_base)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo, body.url_impressao_base)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")


@router.patch("/{id}")
async def atualizar_empresa(id: int, body: EmpresaUpdate, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    if body.sso_query_acesso is not None:
        try:
            validar_sql(body.sso_query_acesso)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    try:
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6,
                db_pass=COALESCE($7, db_pass),
                ativo=$8,
                sso_query_acesso=$9,
                url_impressao_base=$10
            WHERE id=$11
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo,
            body.sso_query_acesso, body.url_impressao_base, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")


@router.delete("/{id}")
async def desativar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    await query_meta("UPDATE empresas SET ativo = false WHERE id = $1", id)
    return {"ok": True}


@router.post("/{id}/reativar")
async def reativar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    await query_meta("UPDATE empresas SET ativo = true WHERE id = $1", id)
    return {"ok": True}


@router.post("/{id}/sso-api-key")
async def gerar_sso_api_key(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    api_key = secrets.token_urlsafe(32)
    api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()

    await query_meta(
        "UPDATE empresas SET sso_api_key_hash = $1 WHERE id = $2",
        api_key_hash, id
    )
    return {"api_key": api_key}


@router.post("/testar-sso-acesso")
async def testar_sso_acesso(body: TestarSsoAcessoInput, user=Depends(require_admin)):
    emp = await query_meta(
        "SELECT slug FROM empresas WHERE id = $1 AND ativo = true", body.empresa_id
    )
    if not emp:
        return {"ok": False, "erro": f"Empresa #{body.empresa_id} não encontrada ou inativa"}

    try:
        validar_sql(body.query)
        rows = await query_company(emp[0]["slug"], body.query, body.codigo_usuario)
        data = [dict(r) for r in rows]
        validar_coluna_painel_slug(data)
        return {"ok": True, "slugs": [r["painel_slug"] for r in data]}
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.post("/{id}/logo")
async def upload_logo(id: int, file: UploadFile = File(...), user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    content = await file.read()
    async with aiofiles.open(f"{LOGOS_DIR}/{id}.png", "wb") as f:
        await f.write(content)
    return {"ok": True, "logo_url": f"/api/empresas/{id}/logo"}


@router.get("/{id}/logo")
async def get_logo(id: int):
    logo_path = f"{LOGOS_DIR}/{id}.png"
    if not await aiofiles.os.path.exists(logo_path):
        raise HTTPException(status_code=404, detail="Logo não encontrado")
    return FileResponse(logo_path, media_type="image/png")
