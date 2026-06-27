from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta

router = APIRouter(prefix="/api/variaveis", tags=["Variáveis"])

TIPOS_VALIDOS = {'date', 'date_range', 'select', 'multiselect', 'text', 'number'}


class VariavelInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    tipo: str
    query_fonte: Optional[str] = None
    param_names: List[str] = []
    ativo: bool = True


@router.get("/")
async def listar_variaveis(user=Depends(get_current_user)):
    rows = await query_meta(
        "SELECT * FROM variaveis WHERE ativo = true ORDER BY nome"
    )
    return [dict(r) for r in rows]


@router.get("/executar-fonte/{variavel_id}")
async def executar_fonte_variavel(variavel_id: int, user=Depends(get_current_user)):
    """Executa a query_fonte da variável no banco da empresa ativa."""
    variavel = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not variavel:
        raise HTTPException(404, "Variável não encontrada")

    v = dict(variavel[0])
    if not v.get("query_fonte"):
        raise HTTPException(400, "Esta variável não tem query_fonte")

    from config.databases import query_company
    try:
        rows = await query_company(user["company_slug"], v["query_fonte"])
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(500, f"Erro ao executar query_fonte: {e}")


@router.get("/{variavel_id}")
async def buscar_variavel(variavel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not rows:
        raise HTTPException(404, "Variável não encontrada")
    return dict(rows[0])


@router.post("/")
async def criar_variavel(body: VariavelInput, user=Depends(require_admin)):
    if body.tipo not in TIPOS_VALIDOS:
        raise HTTPException(400, f"Tipo inválido. Use: {TIPOS_VALIDOS}")
    if body.tipo in ('select', 'multiselect') and not body.query_fonte:
        raise HTTPException(400, "query_fonte é obrigatório para select/multiselect")

    rows = await query_meta("""
        INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, param_names, ativo)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
    """, body.slug, body.nome, body.descricao, body.tipo,
        body.query_fonte, body.param_names, body.ativo)
    return dict(rows[0])


@router.patch("/{variavel_id}")
async def atualizar_variavel(variavel_id: int, body: dict, user=Depends(require_admin)):
    atual = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not atual:
        raise HTTPException(404, "Variável não encontrada")

    campos = []
    valores = []
    for i, (k, v) in enumerate(body.items(), start=1):
        campos.append(f"{k} = ${i}")
        valores.append(v)

    valores.append(variavel_id)
    sql = f"UPDATE variaveis SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
    rows = await query_meta(sql, *valores)
    return dict(rows[0])


@router.delete("/{variavel_id}")
async def deletar_variavel(variavel_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "UPDATE variaveis SET ativo = false WHERE id = $1 RETURNING id, slug",
        variavel_id
    )
    if not rows:
        raise HTTPException(404, "Variável não encontrada")
    return {"desativado": True, "slug": rows[0]["slug"]}
