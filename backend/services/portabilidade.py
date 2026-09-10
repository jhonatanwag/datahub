import base64
from datetime import datetime, timezone

from fastapi import HTTPException

from config.databases import query_meta

FORMATO = "datahub-painel"
VERSAO = 1

QUERY_CAMPOS = [
    "slug", "nome", "descricao", "sql_texto", "tipo", "cache_ttl", "ativo",
    "kpi_cor_fonte", "kpi_cor_fundo", "mapa_camada",
    "chart_fonte_tamanho", "chart_truncar_label", "chart_truncar_tamanho", "chart_mostrar_valor",
    "chart_valor_label", "chart_rotulo_eixo", "chart_rotulo_valor",
    "impressao_habilitada", "impressao_caminho", "impressao_coluna",
    "meta_habilitada", "meta_coluna_valor", "meta_coluna_inicio", "meta_coluna_fim",
    "meta_cor_dentro", "meta_cor_fora",
    "pdf_orientacao", "kpi_imagem_habilitada", "kpi_imagem_posicao",
    "kpi_valor_primeiro", "chart_filtro_coluna",
]
VARIAVEL_CAMPOS = ["slug", "nome", "descricao", "tipo", "query_fonte", "param_names", "ativo"]
PAINEL_CAMPOS = [
    "slug", "nome", "descricao", "icone", "colunas", "linhas_fixas", "total_linhas",
    "ordem_menu", "impressao_orientacao", "ativo",
]
INDICADOR_CAMPOS = ["query_slug", "titulo", "linha", "coluna", "col_span", "row_span", "posicao"]
PAINEL_VARIAVEL_CAMPOS = [
    "obrigatorio", "valor_padrao", "valor_padrao_inicio", "valor_padrao_fim", "posicao",
]


def _b64(dados) -> str | None:
    return base64.b64encode(dados).decode() if dados else None


async def _nome_por_id(tabela: str, col: str, id_):
    if not id_:
        return None
    r = await query_meta(f"SELECT {col} FROM {tabela} WHERE id = $1", id_)
    return r[0][col] if r else None


def _serializar_variavel(row: dict) -> dict:
    out = {c: row[c] for c in VARIAVEL_CAMPOS}
    # asyncpg devolve param_names como list[str] ou None
    out["param_names"] = list(out["param_names"] or [])
    return out


async def _serializar_query(row: dict) -> dict:
    out = {c: row[c] for c in QUERY_CAMPOS}
    out["grupo_nome"] = await _nome_por_id("query_grupos", "nome", row["grupo_id"])
    out["empresa_slug"] = await _nome_por_id("empresas", "slug", row["empresa_id"])
    out["subquery_slug"] = await _nome_por_id("queries", "slug", row["subquery_id"])
    out["kpi_imagem_base64"] = _b64(row.get("kpi_imagem"))
    out["kpi_imagem_mime"] = row.get("kpi_imagem_mime")

    params = await query_meta(
        "SELECT p.nome, p.tipo, p.obrigatorio, p.valor_padrao, p.descricao, p.param_slot, "
        "       v.slug AS variavel_slug "
        "FROM query_parametros p LEFT JOIN variaveis v ON v.id = p.variavel_id "
        "WHERE p.query_id = $1 ORDER BY p.id",
        row["id"],
    )
    out["parametros"] = [dict(r) for r in params]
    out["agrupamentos"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna, ordem FROM query_agrupamentos WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    out["agregacoes"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna, funcao, label, ordem FROM query_agregacoes WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    out["subquery_parametros"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna_origem, parametro_destino, ordem FROM query_subquery_parametros "
            "WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    return out


async def _serializar_painel(row: dict) -> dict:
    out = {c: row[c] for c in PAINEL_CAMPOS}
    out["grupo_nome"] = await _nome_por_id("painel_grupos", "nome", row["grupo_id"])
    out["empresa_slug"] = await _nome_por_id("empresas", "slug", row["empresa_id"])
    out["imagem_base64"] = _b64(row.get("imagem"))
    out["imagem_mime"] = row.get("imagem_mime")

    indicadores = await query_meta(
        "SELECT pi.*, v.slug AS filtro_slug FROM painel_indicadores pi "
        "LEFT JOIN variaveis v ON v.id = pi.filtro_clique_variavel_id "
        "WHERE pi.painel_id = $1 ORDER BY pi.linha, pi.coluna",
        row["id"],
    )
    out["indicadores"] = [
        {**{c: r[c] for c in INDICADOR_CAMPOS}, "filtro_clique_variavel_slug": r["filtro_slug"]}
        for r in indicadores
    ]

    pv = await query_meta(
        "SELECT pv.*, v.slug AS variavel_slug FROM painel_variaveis pv "
        "JOIN variaveis v ON v.id = pv.variavel_id "
        "WHERE pv.painel_id = $1 ORDER BY pv.posicao, pv.id",
        row["id"],
    )
    out["variaveis_painel"] = [
        {**{c: r[c] for c in PAINEL_VARIAVEL_CAMPOS}, "variavel_slug": r["variavel_slug"]}
        for r in pv
    ]
    return out


async def montar_bundle_painel(painel_id: int):
    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        return None
    p = dict(painel_rows[0])
    avisos: list[str] = []

    indicadores = await query_meta(
        "SELECT query_slug FROM painel_indicadores WHERE painel_id = $1", painel_id
    )

    # --- fecho transitivo de queries ---
    visitados: dict[str, dict | None] = {}
    fila = [r["query_slug"] for r in indicadores]
    while fila:
        slug = fila.pop()
        if slug in visitados:
            continue
        qr = await query_meta(
            "SELECT * FROM queries WHERE slug = $1 ORDER BY empresa_id NULLS FIRST LIMIT 1", slug
        )
        if not qr:
            avisos.append(f"Indicador referencia query inexistente: {slug}")
            visitados[slug] = None
            continue
        rowq = dict(qr[0])
        visitados[slug] = rowq
        if rowq["subquery_id"]:
            sub = await query_meta("SELECT slug FROM queries WHERE id = $1", rowq["subquery_id"])
            if sub:
                fila.append(sub[0]["slug"])

    queries_reais = [r for r in visitados.values() if r]

    # --- variáveis referenciadas ---
    var_slugs: set[str] = set()
    pv = await query_meta(
        "SELECT v.slug FROM painel_variaveis pv JOIN variaveis v ON v.id = pv.variavel_id "
        "WHERE pv.painel_id = $1", painel_id)
    var_slugs.update(r["slug"] for r in pv)
    fc = await query_meta(
        "SELECT v.slug FROM painel_indicadores pi JOIN variaveis v ON v.id = pi.filtro_clique_variavel_id "
        "WHERE pi.painel_id = $1", painel_id)
    var_slugs.update(r["slug"] for r in fc)
    for rowq in queries_reais:
        qp = await query_meta(
            "SELECT v.slug FROM query_parametros p JOIN variaveis v ON v.id = p.variavel_id "
            "WHERE p.query_id = $1", rowq["id"])
        var_slugs.update(r["slug"] for r in qp)

    variaveis_out = []
    for slug in sorted(var_slugs):
        vr = await query_meta("SELECT * FROM variaveis WHERE slug = $1", slug)
        if vr:
            variaveis_out.append(_serializar_variavel(dict(vr[0])))

    queries_out = [await _serializar_query(r) for r in queries_reais]

    return {
        "formato": FORMATO,
        "versao": VERSAO,
        "exportado_em": datetime.now(timezone.utc).isoformat(),
        "painel": await _serializar_painel(p),
        "queries": queries_out,
        "variaveis": variaveis_out,
        "avisos": avisos,
    }


def validar_formato(bundle: dict) -> None:
    if not isinstance(bundle, dict) or bundle.get("formato") != FORMATO:
        raise HTTPException(400, "Arquivo não é um export de painel do DataHub")
    if not isinstance(bundle.get("versao"), int) or bundle["versao"] > VERSAO:
        raise HTTPException(400, f"Versão de formato não suportada (máx: {VERSAO})")
    for chave in ("painel", "queries", "variaveis"):
        if chave not in bundle:
            raise HTTPException(400, f"Arquivo incompleto: falta '{chave}'")
