import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta, query_company

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


class TestarFonteInput(BaseModel):
    query_fonte: str
    empresa_id: Optional[int] = None


async def _resolver_company_slug(user, empresa_id: Optional[int]) -> str:
    """Resolve o slug da empresa a usar para testar uma query_fonte: a
    empresa escolhida explicitamente (dropdown 'Testar na empresa') ou,
    na ausência dela, a empresa ativa do usuário logado."""
    if not empresa_id:
        return user["company_slug"]

    emp = await query_meta(
        "SELECT slug FROM empresas WHERE id = $1 AND ativo = true", empresa_id
    )
    if not emp:
        raise ValueError(f"Empresa #{empresa_id} não encontrada ou inativa")
    return emp[0]["slug"]


def _validar_colunas_valor_label(data: List[dict]) -> None:
    """A query_fonte de select/multiselect precisa retornar colunas chamadas
    exatamente 'valor' e 'label' (o frontend lê essas chaves literalmente).
    Sem essa checagem, uma query com colunas de outro nome roda com sucesso
    e devolve linhas, mas a tabela de opções fica em branco silenciosamente."""
    if data and not ("valor" in data[0] and "label" in data[0]):
        colunas = list(data[0].keys())
        raise ValueError(
            f"A query retornou as colunas {colunas}, mas era esperado 'valor' e 'label'. "
            f"Use aliases, ex: SELECT id AS valor, nome AS label FROM tabela"
        )


@router.get("/")
async def listar_variaveis(user=Depends(get_current_user)):
    rows = await query_meta(
        "SELECT * FROM variaveis WHERE ativo = true ORDER BY nome"
    )
    return [dict(r) for r in rows]


@router.get("/executar-fonte/{variavel_id}")
async def executar_fonte_variavel(
    variavel_id: int, empresa_id: Optional[int] = None, user=Depends(get_current_user)
):
    """Executa a query_fonte da variável no banco da empresa escolhida
    (ou, na ausência de `empresa_id`, na empresa ativa do usuário)."""
    variavel = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not variavel:
        raise HTTPException(404, "Variável não encontrada")

    v = dict(variavel[0])
    if not v.get("query_fonte"):
        raise HTTPException(400, "Esta variável não tem query_fonte")

    try:
        company_slug = await _resolver_company_slug(user, empresa_id)
        rows = await query_company(company_slug, v["query_fonte"])
        data = [dict(r) for r in rows]
        _validar_colunas_valor_label(data)
        return data
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erro ao executar query_fonte: {e}")


@router.post("/testar-fonte")
async def testar_fonte_variavel(body: TestarFonteInput, user=Depends(require_admin)):
    """Executa a query_fonte informada direto no banco da empresa escolhida,
    sem persistir nenhuma variável — usado pelo botão 'Testar Query' antes de salvar."""
    try:
        company_slug = await _resolver_company_slug(user, body.empresa_id)
        rows = await query_company(company_slug, body.query_fonte)
        data = [dict(r) for r in rows]
        _validar_colunas_valor_label(data)
        return {"ok": True, "linhas": len(data), "amostra": data[:5]}
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


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

    try:
        rows = await query_meta("""
            INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, param_names, ativo)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.tipo,
            body.query_fonte, body.param_names, body.ativo)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Já existe uma variável com esse slug")


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
