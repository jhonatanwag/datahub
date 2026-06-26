import bcrypt
import asyncpg
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from config.databases import query_meta
from middleware.auth import require_admin

router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])


class UsuarioInput(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "viewer"
    ativo: bool = True


class VincularEmpresasInput(BaseModel):
    empresa_ids: List[int]


@router.get("/")
async def listar_usuarios(user=Depends(require_admin)):
    usuarios = await query_meta(
        "SELECT id, nome, email, role, ativo, criado_em FROM usuarios ORDER BY nome"
    )
    result = []
    for u in usuarios:
        empresas = await query_meta("""
            SELECT e.id, e.nome, e.slug
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
        """, u["id"])
        result.append({**dict(u), "empresas": [dict(e) for e in empresas]})
    return result


@router.post("/")
async def criar_usuario(body: UsuarioInput, user=Depends(require_admin)):
    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
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
        senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()

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
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    await query_meta("DELETE FROM usuario_empresas WHERE usuario_id = $1", id)
    for empresa_id in body.empresa_ids:
        await query_meta(
            "INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            id, empresa_id
        )
    return {"ok": True, "empresa_ids": body.empresa_ids}


@router.get("/{id}/empresas")
async def listar_empresas_usuario(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    empresas = await query_meta("""
        SELECT e.id, e.slug, e.nome, e.ativo
        FROM empresas e
        JOIN usuario_empresas ue ON ue.empresa_id = e.id
        WHERE ue.usuario_id = $1
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
