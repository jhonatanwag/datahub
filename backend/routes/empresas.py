import os
import asyncpg
import aiofiles
import aiofiles.os
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from config.databases import query_meta
from middleware.auth import require_admin

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


class TestarConexaoInput(BaseModel):
    host: str
    port: int
    database: str
    user: str
    password: str


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
        "SELECT id, slug, nome, db_host, db_port, db_name, ativo, criado_em FROM empresas WHERE id = $1",
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
        await conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Conexão com o banco falhou: {e}")

    try:
        rows = await query_meta("""
            INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")


@router.patch("/{id}")
async def atualizar_empresa(id: int, body: EmpresaInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    try:
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6, db_pass=$7, ativo=$8
            WHERE id=$9
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo, id)
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
