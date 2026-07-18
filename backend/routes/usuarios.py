import json
import asyncio
from functools import partial
import bcrypt
import asyncpg
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from config.databases import query_meta, get_meta_pool
from middleware.auth import require_admin

router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])


class UsuarioInput(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "viewer"
    ativo: bool = True


class VinculoEmpresa(BaseModel):
    empresa_id: int
    codigo_usuario_externo: str | None = None


class VincularEmpresasInput(BaseModel):
    vinculos: List[VinculoEmpresa]


async def _hash_senha(senha: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
    )


@router.get("/")
async def listar_usuarios(user=Depends(require_admin)):
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.id, u.nome, u.email, u.role, u.ativo, u.criado_em,
                   COALESCE(
                       json_agg(json_build_object('id', e.id, 'nome', e.nome, 'slug', e.slug))
                       FILTER (WHERE e.id IS NOT NULL AND e.ativo = true),
                       '[]'::json
                   ) AS empresas
            FROM usuarios u
            LEFT JOIN usuario_empresas ue ON ue.usuario_id = u.id
            LEFT JOIN empresas e ON e.id = ue.empresa_id
            GROUP BY u.id
            ORDER BY u.nome
        """)
    result = []
    for r in rows:
        row = dict(r)
        raw = row.get("empresas")
        if isinstance(raw, str):
            row["empresas"] = json.loads(raw)
        result.append(row)
    return result


@router.post("/")
async def criar_usuario(body: UsuarioInput, user=Depends(require_admin)):
    senha_hash = await _hash_senha(body.senha)
    try:
        rows = await query_meta("""
            INSERT INTO usuarios (nome, email, senha_hash, role, ativo)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, nome, email, role, ativo
        """, body.nome, body.email, senha_hash, body.role, body.ativo)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email já está em uso")


@router.patch("/{id}")
async def atualizar_usuario(id: int, body: UsuarioInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT id, senha_hash FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if body.senha == "UNCHANGED":
        senha_hash = rows[0]["senha_hash"]
    else:
        senha_hash = await _hash_senha(body.senha)

    try:
        rows = await query_meta("""
            UPDATE usuarios
            SET nome=$1, email=$2, senha_hash=$3, role=$4, ativo=$5
            WHERE id=$6
            RETURNING id, nome, email, role, ativo
        """, body.nome, body.email, senha_hash, body.role, body.ativo, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email já está em uso")


@router.delete("/{id}")
async def desativar_usuario(id: int, user=Depends(require_admin)):
    if id == user["id"]:
        raise HTTPException(status_code=400, detail="Não é possível desativar o próprio usuário")
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    await query_meta("UPDATE usuarios SET ativo = false WHERE id = $1", id)
    return {"ok": True}


@router.post("/{id}/empresas")
async def vincular_empresas(id: int, body: VincularEmpresasInput, user=Depends(require_admin)):
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM usuarios WHERE id = $1", id)
        if not rows:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        async with conn.transaction():
            # Only replace links to active empresas; inactive links are preserved
            await conn.execute("""
                DELETE FROM usuario_empresas
                WHERE usuario_id = $1
                  AND empresa_id IN (SELECT id FROM empresas WHERE ativo = true)
            """, id)
            for vinculo in body.vinculos:
                await conn.execute(
                    """
                    INSERT INTO usuario_empresas (usuario_id, empresa_id, codigo_usuario_externo)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (usuario_id, empresa_id)
                    DO UPDATE SET codigo_usuario_externo = EXCLUDED.codigo_usuario_externo
                    """,
                    id, vinculo.empresa_id, vinculo.codigo_usuario_externo
                )
    return {"ok": True, "vinculos": [v.dict() for v in body.vinculos]}


@router.get("/{id}/empresas")
async def listar_empresas_usuario(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    empresas = await query_meta("""
        SELECT e.id, e.slug, e.nome, e.ativo, ue.codigo_usuario_externo
        FROM empresas e
        JOIN usuario_empresas ue ON ue.empresa_id = e.id
        WHERE ue.usuario_id = $1 AND e.ativo = true
        ORDER BY e.nome
    """, id)
    return [dict(e) for e in empresas]


@router.delete("/{id}/empresas/{empresa_id}")
async def remover_vinculo(id: int, empresa_id: int, user=Depends(require_admin)):
    await query_meta(
        "DELETE FROM usuario_empresas WHERE usuario_id = $1 AND empresa_id = $2",
        id, empresa_id
    )
    return {"ok": True}
