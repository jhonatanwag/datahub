import json
import logging
import re
from typing import Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config.databases import query_meta, meta_tx
from middleware.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/apresentacoes", tags=["Apresentações"])
logger = logging.getLogger("datahub")

SLUG_RE = re.compile(r"^[a-z0-9_]+$")
CAMPOS_EDITAVEIS = {"slug", "nome", "descricao", "empresa_id", "intervalo_atualizacao_seg", "ativo"}


class ApresentacaoInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    empresa_id: Optional[int] = None
    intervalo_atualizacao_seg: int = Field(300, ge=30, le=86400)
    ativo: bool = True


class SlideInput(BaseModel):
    painel_id: int
    duracao_seg: int = Field(30, ge=5, le=3600)
    filtros: Dict[str, str] = {}


def _bloquear_externo(user):
    if user["role"] == "externo":
        raise HTTPException(403, "Apresentações não estão disponíveis para este perfil")


def _validar_slug(slug: str):
    if not SLUG_RE.match(slug):
        raise HTTPException(422, "Slug deve conter apenas letras minúsculas, números e _")


def _slide_dict(row) -> dict:
    d = dict(row)
    d["filtros"] = json.loads(d["filtros"]) if d.get("filtros") else {}
    return d


# ── Rotas do usuário (estáticas antes das dinâmicas) ─────────

@router.get("/minhas")
async def minhas(user=Depends(get_current_user)):
    _bloquear_externo(user)
    base = """
        SELECT a.id, a.slug, a.nome, a.descricao,
               (SELECT COUNT(*)::int FROM apresentacao_slides s WHERE s.apresentacao_id = a.id) AS total_slides
        FROM apresentacoes a
    """
    if user["role"] == "admin":
        rows = await query_meta(base + """
            WHERE a.ativo = true AND (a.empresa_id = $1 OR a.empresa_id IS NULL)
            ORDER BY a.nome
        """, user["empresa_id"])
    else:
        rows = await query_meta(base + """
            JOIN apresentacao_usuarios au ON au.apresentacao_id = a.id
            WHERE au.usuario_id = $1 AND a.ativo = true
              AND (a.empresa_id = $2 OR a.empresa_id IS NULL)
            ORDER BY a.nome
        """, user["id"], user["empresa_id"])
    return [dict(r) for r in rows]


@router.get("/{apresentacao_id}/executar")
async def executar(apresentacao_id: int, user=Depends(get_current_user)):
    _bloquear_externo(user)
    rows = await query_meta("""
        SELECT id, slug, nome, descricao, intervalo_atualizacao_seg
        FROM apresentacoes
        WHERE id = $1 AND ativo = true AND (empresa_id = $2 OR empresa_id IS NULL)
    """, apresentacao_id, user["empresa_id"])
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada ou sem acesso")
    if user["role"] != "admin":
        vinculo = await query_meta(
            "SELECT 1 FROM apresentacao_usuarios WHERE apresentacao_id = $1 AND usuario_id = $2",
            apresentacao_id, user["id"],
        )
        if not vinculo:
            raise HTTPException(404, "Apresentação não encontrada ou sem acesso")

    slides_rows = await query_meta("""
        SELECT s.id, s.ordem, s.duracao_seg, s.filtros::text AS filtros,
               p.id AS p_id, p.slug AS p_slug, p.nome AS p_nome,
               p.descricao AS p_descricao, p.colunas AS p_colunas
        FROM apresentacao_slides s
        JOIN paineis p ON p.id = s.painel_id
        WHERE s.apresentacao_id = $1 AND p.ativo = true
          AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
        ORDER BY s.ordem, s.id
    """, apresentacao_id, user["empresa_id"])
    slides = []
    for r in slides_rows:
        slides.append({
            "id": r["id"],
            "ordem": r["ordem"],
            "duracao_seg": r["duracao_seg"],
            "filtros": json.loads(r["filtros"]) if r["filtros"] else {},
            "painel": {
                "id": r["p_id"], "slug": r["p_slug"], "nome": r["p_nome"],
                "descricao": r["p_descricao"], "colunas": r["p_colunas"],
            },
        })
    return {**dict(rows[0]), "slides": slides}


# ── CRUD (admin) ─────────────────────────────────────────────

@router.get("/")
async def listar(user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT a.*,
               (SELECT COUNT(*)::int FROM apresentacao_slides s WHERE s.apresentacao_id = a.id) AS total_slides
        FROM apresentacoes a
        ORDER BY a.nome
    """)
    return [dict(r) for r in rows]


@router.post("/")
async def criar(body: ApresentacaoInput, user=Depends(require_admin)):
    _validar_slug(body.slug)
    try:
        rows = await query_meta("""
            INSERT INTO apresentacoes (slug, nome, descricao, empresa_id, intervalo_atualizacao_seg, ativo)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING *
        """, body.slug, body.nome, body.descricao, body.empresa_id,
            body.intervalo_atualizacao_seg, body.ativo)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Já existe uma apresentação com esse slug")
    return dict(rows[0])


@router.get("/{apresentacao_id}")
async def buscar(apresentacao_id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT * FROM apresentacoes WHERE id = $1", apresentacao_id)
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada")
    return dict(rows[0])


@router.patch("/{apresentacao_id}")
async def atualizar(apresentacao_id: int, body: dict, user=Depends(require_admin)):
    campos = {k: v for k, v in body.items() if k in CAMPOS_EDITAVEIS}
    if not campos:
        raise HTTPException(400, "Nenhum campo válido para atualizar")
    if "slug" in campos:
        _validar_slug(campos["slug"])
    if "intervalo_atualizacao_seg" in campos and int(campos["intervalo_atualizacao_seg"]) < 30:
        raise HTTPException(422, "Intervalo mínimo é 30 segundos")
    sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(campos))  # chaves vêm da whitelist
    try:
        rows = await query_meta(
            f"UPDATE apresentacoes SET {sets} WHERE id = $1 RETURNING *",
            apresentacao_id, *campos.values(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Já existe uma apresentação com esse slug")
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada")
    return dict(rows[0])


@router.delete("/{apresentacao_id}")
async def desativar(apresentacao_id: int, user=Depends(require_admin)):
    await query_meta("UPDATE apresentacoes SET ativo = false WHERE id = $1", apresentacao_id)
    return {"ok": True}


@router.delete("/{apresentacao_id}/permanente")
async def deletar_permanente(apresentacao_id: int, user=Depends(require_admin)):
    await query_meta("DELETE FROM apresentacoes WHERE id = $1", apresentacao_id)
    return {"ok": True}


# ── Slides ───────────────────────────────────────────────────

async def _listar_slides(apresentacao_id: int) -> list:
    rows = await query_meta("""
        SELECT s.id, s.painel_id, s.ordem, s.duracao_seg, s.filtros::text AS filtros,
               p.nome AS painel_nome, p.slug AS painel_slug, p.ativo AS painel_ativo
        FROM apresentacao_slides s
        JOIN paineis p ON p.id = s.painel_id
        WHERE s.apresentacao_id = $1
        ORDER BY s.ordem, s.id
    """, apresentacao_id)
    return [_slide_dict(r) for r in rows]


@router.get("/{apresentacao_id}/slides")
async def listar_slides(apresentacao_id: int, user=Depends(require_admin)):
    return await _listar_slides(apresentacao_id)


@router.put("/{apresentacao_id}/slides")
async def salvar_slides(apresentacao_id: int, slides: List[SlideInput], user=Depends(require_admin)):
    existe = await query_meta("SELECT 1 FROM apresentacoes WHERE id = $1", apresentacao_id)
    if not existe:
        raise HTTPException(404, "Apresentação não encontrada")
    ids = list({s.painel_id for s in slides})
    if ids:
        achados = await query_meta("SELECT id FROM paineis WHERE id = ANY($1::int[])", ids)
        if len(achados) != len(ids):
            raise HTTPException(422, "Há slide apontando para um painel que não existe")
    async with meta_tx() as conn:
        await conn.execute("DELETE FROM apresentacao_slides WHERE apresentacao_id = $1", apresentacao_id)
        for i, s in enumerate(slides):
            await conn.execute("""
                INSERT INTO apresentacao_slides (apresentacao_id, painel_id, ordem, duracao_seg, filtros)
                VALUES ($1,$2,$3,$4,$5::jsonb)
            """, apresentacao_id, s.painel_id, i, s.duracao_seg, json.dumps(s.filtros))
    return await _listar_slides(apresentacao_id)


# ── Usuários com acesso ──────────────────────────────────────

@router.get("/{apresentacao_id}/usuarios")
async def listar_usuarios(apresentacao_id: int, user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT u.id, u.nome, u.email, u.role
        FROM usuarios u
        JOIN apresentacao_usuarios au ON au.usuario_id = u.id
        WHERE au.apresentacao_id = $1
    """, apresentacao_id)
    return [dict(r) for r in rows]


@router.put("/{apresentacao_id}/usuarios")
async def salvar_usuarios(apresentacao_id: int, usuario_ids: List[int], user=Depends(require_admin)):
    async with meta_tx() as conn:
        await conn.execute("DELETE FROM apresentacao_usuarios WHERE apresentacao_id = $1", apresentacao_id)
        for uid in usuario_ids:
            await conn.execute(
                "INSERT INTO apresentacao_usuarios (apresentacao_id, usuario_id) VALUES ($1,$2)",
                apresentacao_id, uid,
            )
    return {"ok": True, "usuarios": usuario_ids}
