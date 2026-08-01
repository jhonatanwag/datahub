from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Response
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta

router = APIRouter(prefix="/api/paineis", tags=["Painéis"])


def _com_imagem_url(row: dict) -> dict:
    """Substitui a coluna bytea `imagem` (nunca deve ir pro JSON) por uma
    URL, só quando o painel de fato tem imagem salva."""
    tem_imagem = row.pop("tem_imagem", None)
    if tem_imagem is None:
        tem_imagem = row.pop("imagem", None) is not None
    else:
        row.pop("imagem", None)
    row.pop("imagem_mime", None)
    row["imagem_url"] = f"/api/paineis/{row['id']}/imagem" if tem_imagem else None
    return row


class PainelInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    icone: str = 'chart-bar'
    colunas: int = 3
    linhas_fixas: bool = False
    total_linhas: Optional[int] = None
    empresa_id: Optional[int] = None
    ativo: bool = True
    ordem_menu: int = 0


class IndicadorInput(BaseModel):
    query_slug: str
    titulo: Optional[str] = None
    linha: int
    coluna: int
    col_span: int = 1
    row_span: int = 1
    posicao: int = 0


class VariavelPainelInput(BaseModel):
    variavel_id: int
    obrigatorio: bool = False
    valor_padrao: Optional[str] = None
    valor_padrao_inicio: Optional[str] = None  # date_range: slot início
    valor_padrao_fim: Optional[str] = None      # date_range: slot fim
    posicao: int = 0


# ── Rotas estáticas ANTES das dinâmicas ──────────────────────

@router.get("/meu-menu")
async def meu_menu(user=Depends(get_current_user)):
    if user["role"] == "externo":
        rows = await query_meta("""
            SELECT id, slug, nome, icone, ordem_menu, empresa_id
            FROM paineis
            WHERE slug = ANY($1::text[])
              AND ativo = true
              AND (empresa_id = $2 OR empresa_id IS NULL)
            ORDER BY ordem_menu
        """, user["paineis_liberados"], user["empresa_id"])
        return sorted([dict(r) for r in rows], key=lambda x: x["ordem_menu"])

    rows = await query_meta("""
        SELECT DISTINCT ON (p.slug)
            p.id, p.slug, p.nome, p.icone, p.ordem_menu, p.empresa_id
        FROM paineis p
        JOIN painel_usuarios pu ON pu.painel_id = p.id
        WHERE pu.usuario_id = $1
          AND p.ativo = true
          AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
        ORDER BY p.slug, p.empresa_id NULLS LAST, p.ordem_menu
    """, user["id"], user["empresa_id"])
    return sorted([dict(r) for r in rows], key=lambda x: x["ordem_menu"])


@router.get("/meu-dashboard")
async def meu_dashboard(user=Depends(get_current_user)):
    if user["role"] == "externo":
        rows = await query_meta("""
            SELECT p.id, p.slug, p.nome, p.descricao, p.icone, p.ordem_menu,
                (p.imagem IS NOT NULL) AS tem_imagem,
                (SELECT COUNT(*)::int FROM painel_indicadores pi WHERE pi.painel_id = p.id) AS total_indicadores
            FROM paineis p
            WHERE p.slug = ANY($1::text[])
              AND p.ativo = true
              AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
            ORDER BY p.ordem_menu
        """, user["paineis_liberados"], user["empresa_id"])
        return sorted([_com_imagem_url(dict(r)) for r in rows], key=lambda x: x["ordem_menu"])

    rows = await query_meta("""
        SELECT DISTINCT ON (p.slug)
            p.id, p.slug, p.nome, p.descricao, p.icone, p.ordem_menu,
            (p.imagem IS NOT NULL) AS tem_imagem,
            (SELECT COUNT(*)::int FROM painel_indicadores pi WHERE pi.painel_id = p.id) AS total_indicadores
        FROM paineis p
        JOIN painel_usuarios pu ON pu.painel_id = p.id
        WHERE pu.usuario_id = $1
          AND p.ativo = true
          AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
        ORDER BY p.slug, p.empresa_id NULLS LAST, p.ordem_menu
    """, user["id"], user["empresa_id"])
    return sorted([_com_imagem_url(dict(r)) for r in rows], key=lambda x: x["ordem_menu"])


@router.get("/slug/{slug}")
async def buscar_painel_por_slug(slug: str, user=Depends(get_current_user)):
    if user["role"] == "externo":
        if slug not in user["paineis_liberados"]:
            raise HTTPException(403, "Sem acesso a este painel")
        rows = await query_meta("""
            SELECT * FROM paineis
            WHERE slug = $1 AND (empresa_id = $2 OR empresa_id IS NULL) AND ativo = true
        """, slug, user["empresa_id"])
        if not rows:
            raise HTTPException(404, "Painel não encontrado")
        return _com_imagem_url(dict(rows[0]))

    rows = await query_meta("""
        SELECT DISTINCT ON (p.slug) p.*
        FROM paineis p
        JOIN painel_usuarios pu ON pu.painel_id = p.id
        WHERE p.slug = $1
          AND pu.usuario_id = $2
          AND p.ativo = true
          AND (p.empresa_id = $3 OR p.empresa_id IS NULL)
        ORDER BY p.slug, p.empresa_id NULLS LAST
    """, slug, user["id"], user["empresa_id"])
    if not rows:
        raise HTTPException(404, "Painel não encontrado ou sem acesso")
    return _com_imagem_url(dict(rows[0]))


# ── CRUD Painéis ─────────────────────────────────────────────

@router.get("/")
async def listar_paineis(user=Depends(get_current_user)):
    if user["role"] == "admin":
        rows = await query_meta("SELECT * FROM paineis ORDER BY ordem_menu, nome")
    else:
        rows = await query_meta("""
            SELECT p.* FROM paineis p
            JOIN painel_usuarios pu ON pu.painel_id = p.id
            WHERE pu.usuario_id = $1 AND p.ativo = true
            ORDER BY p.ordem_menu, p.nome
        """, user["id"])
    return [_com_imagem_url(dict(r)) for r in rows]


@router.get("/{painel_id}")
async def buscar_painel(painel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    return _com_imagem_url(dict(rows[0]))


@router.post("/")
async def criar_painel(body: PainelInput, user=Depends(require_admin)):
    rows = await query_meta("""
        INSERT INTO paineis
            (slug, nome, descricao, icone, colunas, linhas_fixas,
             total_linhas, empresa_id, ativo, ordem_menu)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING *
    """, body.slug, body.nome, body.descricao, body.icone,
        body.colunas, body.linhas_fixas, body.total_linhas,
        body.empresa_id, body.ativo, body.ordem_menu)
    return _com_imagem_url(dict(rows[0]))


@router.patch("/{painel_id}")
async def atualizar_painel(painel_id: int, body: dict, user=Depends(require_admin)):
    atual = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not atual:
        raise HTTPException(404, "Painel não encontrado")

    campos = []
    valores = []
    for i, (k, v) in enumerate(body.items(), start=1):
        campos.append(f"{k} = ${i}")
        valores.append(v)

    valores.append(painel_id)
    sql = f"UPDATE paineis SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
    rows = await query_meta(sql, *valores)
    return _com_imagem_url(dict(rows[0]))


@router.delete("/{painel_id}")
async def desativar_painel(painel_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "UPDATE paineis SET ativo = false WHERE id = $1 RETURNING id, slug",
        painel_id
    )
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    return {"desativado": True, "slug": rows[0]["slug"]}


@router.post("/{painel_id}/imagem")
async def upload_imagem(painel_id: int, file: UploadFile = File(...), user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM paineis WHERE id = $1", painel_id)
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    content = await file.read()
    await query_meta(
        "UPDATE paineis SET imagem = $1, imagem_mime = $2 WHERE id = $3",
        content, file.content_type or "image/png", painel_id
    )
    return {"ok": True, "imagem_url": f"/api/paineis/{painel_id}/imagem"}


@router.get("/{painel_id}/imagem")
async def get_imagem(painel_id: int):
    rows = await query_meta("SELECT imagem, imagem_mime FROM paineis WHERE id = $1", painel_id)
    if not rows or rows[0]["imagem"] is None:
        raise HTTPException(404, "Imagem não encontrada")
    return Response(content=rows[0]["imagem"], media_type=rows[0]["imagem_mime"] or "image/png")


# ── Indicadores do painel ─────────────────────────────────────

@router.get("/{painel_id}/indicadores")
async def listar_indicadores(painel_id: int, user=Depends(get_current_user)):
    if user["role"] == "externo":
        painel_rows = await query_meta("SELECT slug FROM paineis WHERE id = $1", painel_id)
        if not painel_rows or painel_rows[0]["slug"] not in user["paineis_liberados"]:
            raise HTTPException(403, "Sem acesso a este painel")

    rows = await query_meta("""
        SELECT pi.*, q.nome AS query_nome, q.tipo AS query_tipo
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
    return [dict(r) for r in rows]


@router.post("/{painel_id}/indicadores")
async def adicionar_indicador(painel_id: int, body: IndicadorInput, user=Depends(require_admin)):
    q = await query_meta("SELECT id FROM queries WHERE slug = $1", body.query_slug)
    if not q:
        raise HTTPException(404, f"Query '{body.query_slug}' não encontrada")
    rows = await query_meta("""
        INSERT INTO painel_indicadores
            (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING *
    """, painel_id, body.query_slug, body.titulo,
        body.linha, body.coluna, body.col_span, body.row_span, body.posicao)
    return dict(rows[0])


@router.put("/{painel_id}/indicadores")
async def salvar_indicadores(
    painel_id: int, indicadores: List[IndicadorInput], user=Depends(require_admin)
):
    await query_meta("DELETE FROM painel_indicadores WHERE painel_id = $1", painel_id)
    resultado = []
    for ind in indicadores:
        rows = await query_meta("""
            INSERT INTO painel_indicadores
                (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING *
        """, painel_id, ind.query_slug, ind.titulo,
            ind.linha, ind.coluna, ind.col_span, ind.row_span, ind.posicao)
        resultado.append(dict(rows[0]))
    return resultado


@router.delete("/{painel_id}/indicadores/{indicador_id}")
async def remover_indicador(painel_id: int, indicador_id: int, user=Depends(require_admin)):
    await query_meta(
        "DELETE FROM painel_indicadores WHERE id = $1 AND painel_id = $2",
        indicador_id, painel_id
    )
    return {"removido": True}


# ── Variáveis (filtros) do painel ─────────────────────────────

@router.get("/{painel_id}/variaveis")
async def listar_variaveis_painel(painel_id: int, user=Depends(get_current_user)):
    if user["role"] == "externo":
        painel_rows = await query_meta("SELECT slug FROM paineis WHERE id = $1", painel_id)
        if not painel_rows or painel_rows[0]["slug"] not in user["paineis_liberados"]:
            raise HTTPException(403, "Sem acesso a este painel")

    rows = await query_meta("""
        SELECT pv.*, v.slug, v.nome, v.tipo, v.query_fonte, v.param_names
        FROM painel_variaveis pv
        JOIN variaveis v ON v.id = pv.variavel_id
        WHERE pv.painel_id = $1
        ORDER BY pv.posicao
    """, painel_id)
    return [dict(r) for r in rows]


@router.put("/{painel_id}/variaveis")
async def salvar_variaveis_painel(
    painel_id: int, variaveis: List[VariavelPainelInput], user=Depends(require_admin)
):
    await query_meta("DELETE FROM painel_variaveis WHERE painel_id = $1", painel_id)
    resultado = []
    for v in variaveis:
        rows = await query_meta("""
            INSERT INTO painel_variaveis
                (painel_id, variavel_id, obrigatorio, valor_padrao, valor_padrao_inicio, valor_padrao_fim, posicao)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING *
        """, painel_id, v.variavel_id, v.obrigatorio, v.valor_padrao,
             v.valor_padrao_inicio, v.valor_padrao_fim, v.posicao)
        resultado.append(dict(rows[0]))
    return resultado


# ── Usuários com acesso ao painel ─────────────────────────────

@router.get("/{painel_id}/usuarios")
async def listar_usuarios_painel(painel_id: int, user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT u.id, u.nome, u.email, u.role
        FROM usuarios u
        JOIN painel_usuarios pu ON pu.usuario_id = u.id
        WHERE pu.painel_id = $1
    """, painel_id)
    return [dict(r) for r in rows]


@router.put("/{painel_id}/usuarios")
async def salvar_usuarios_painel(
    painel_id: int, usuario_ids: List[int], user=Depends(require_admin)
):
    await query_meta("DELETE FROM painel_usuarios WHERE painel_id = $1", painel_id)
    for uid in usuario_ids:
        await query_meta(
            "INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES ($1, $2)",
            painel_id, uid
        )
    return {"ok": True, "usuarios": usuario_ids}


# ── Renderizar painel completo ────────────────────────────────

@router.get("/{painel_id}/renderizar")
async def renderizar_painel(
    painel_id: int,
    request: Request,
    user=Depends(get_current_user)
):
    """
    Executa todas as queries do painel com os filtros aplicados.
    Filtros chegam como query params: ?data_inicio=2026-01-01&data_fim=2026-06-30
    """
    from services.query_runner import resolver_query

    filtros = dict(request.query_params)

    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        raise HTTPException(404, "Painel não encontrado")

    if user["role"] == "externo":
        if painel_rows[0]["slug"] not in user["paineis_liberados"]:
            raise HTTPException(403, "Sem acesso a este painel")
        filtros["codigo_usuario_externo"] = user["codigo_usuario"]
    elif user.get("codigo_usuario_externo"):
        filtros["codigo_usuario_externo"] = user["codigo_usuario_externo"]

    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label, q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna,
               q.meta_habilitada, q.meta_coluna_valor, q.meta_coluna_inicio, q.meta_coluna_fim,
               q.meta_cor_dentro, q.meta_cor_fora
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)

    resultado = []
    for ind in indicadores:
        ind_dict = dict(ind)
        try:
            dados = await resolver_query(
                slug=ind_dict["query_slug"],
                company_slug=user["company_slug"],
                empresa_id=user["empresa_id"],
                parametros=filtros
            )
            ind_dict["dados"] = dados.get("data")
            ind_dict["query_tipo"] = dados.get("tipo")
            ind_dict["erro"] = None
        except Exception as e:
            ind_dict["dados"] = None
            ind_dict["query_tipo"] = None
            ind_dict["erro"] = str(e)
        resultado.append(ind_dict)

    return {
        "painel": dict(painel_rows[0]),
        "indicadores": resultado,
        "url_impressao_base": user.get("url_impressao_base")
    }
