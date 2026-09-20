import base64
from datetime import datetime, timezone

from fastapi import HTTPException

from config.databases import query_meta, meta_tx
from services.grupos import resolver_grupo_id
from services.query_runner import invalidar_cache_query, validar_sql

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
    "pivot_coluna", "pivot_ordem_coluna", "pivot_total",
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
    out["base_query_slug"] = await _nome_por_id("queries", "slug", row["query_base_id"])
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
        if rowq["query_base_id"]:
            base = await query_meta("SELECT slug FROM queries WHERE id = $1", rowq["query_base_id"])
            if base:
                fila.append(base[0]["slug"])

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

    # shape do payload interno — evita KeyError/TypeError virarem HTTP 500
    painel = bundle["painel"]
    if not isinstance(painel, dict) or not painel.get("slug"):
        raise HTTPException(400, "Arquivo inválido: 'painel' precisa ser um objeto com 'slug'")
    for chave in ("queries", "variaveis"):
        lista = bundle[chave]
        if not isinstance(lista, list):
            raise HTTPException(400, f"Arquivo inválido: '{chave}' precisa ser uma lista")
        for item in lista:
            if not isinstance(item, dict) or not item.get("slug"):
                raise HTTPException(400, f"Arquivo inválido: cada item de '{chave}' precisa ter 'slug'")


# --- Task 3: análise de import (diff sem gravar) ---------------------------------

# chaves comparadas por entidade (topo + arrays-filhos)
_PAINEL_DIFF_KEYS = PAINEL_CAMPOS + [
    "grupo_nome", "empresa_slug", "imagem_base64", "imagem_mime",
    "indicadores", "variaveis_painel",
]
_QUERY_DIFF_KEYS = QUERY_CAMPOS + [
    "grupo_nome", "empresa_slug", "subquery_slug", "base_query_slug", "kpi_imagem_base64", "kpi_imagem_mime",
    "parametros", "agrupamentos", "agregacoes", "subquery_parametros",
]
_VARIAVEL_DIFF_KEYS = VARIAVEL_CAMPOS


def _comparar(atual: dict, novo: dict, keys) -> list[str]:
    difs = []
    for k in keys:
        if atual.get(k) != novo.get(k):
            difs.append(k)
    return difs


async def _empresa_id_de_slug(slug):
    if not slug:
        return None
    r = await query_meta("SELECT id FROM empresas WHERE slug = $1", slug)
    return r[0]["id"] if r else None


async def _classificar_query(qb: dict) -> dict:
    emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
    existente = await query_meta(
        "SELECT * FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        qb["slug"], emp_id,
    )
    base = {"slug": qb["slug"], "nome": qb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = await _serializar_query(dict(existente[0]))
    difs = _comparar(atual, qb, _QUERY_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def _classificar_variavel(vb: dict) -> dict:
    existente = await query_meta("SELECT * FROM variaveis WHERE slug = $1", vb["slug"])
    base = {"slug": vb["slug"], "nome": vb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = _serializar_variavel(dict(existente[0]))
    difs = _comparar(atual, vb, _VARIAVEL_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def _classificar_painel(pb: dict) -> dict:
    existente = await query_meta("SELECT * FROM paineis WHERE slug = $1", pb["slug"])
    base = {"slug": pb["slug"], "nome": pb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = await _serializar_painel(dict(existente[0]))
    difs = _comparar(atual, pb, _PAINEL_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def analisar_bundle(bundle: dict) -> dict:
    validar_formato(bundle)
    avisos: list[str] = []

    plano = {
        "painel": await _classificar_painel(bundle["painel"]),
        "queries": [await _classificar_query(q) for q in bundle["queries"]],
        "variaveis": [await _classificar_variavel(v) for v in bundle["variaveis"]],
    }

    # aviso: empresa_slug do bundle não existe no destino
    slugs_emp = {e for e in (
        [bundle["painel"].get("empresa_slug")] + [q.get("empresa_slug") for q in bundle["queries"]]
    ) if e}
    for s in sorted(slugs_emp):
        if await _empresa_id_de_slug(s) is None:
            avisos.append(f"Empresa '{s}' não existe no destino — entidade entrará como global")

    # aviso: dependência referenciada que não está no bundle e não existe no destino
    slugs_query_bundle = {q["slug"] for q in bundle["queries"]}
    for ind in bundle["painel"].get("indicadores", []):
        qs = ind["query_slug"]
        if qs not in slugs_query_bundle:
            existe = await query_meta("SELECT 1 FROM queries WHERE slug = $1", qs)
            if not existe:
                avisos.append(f"Dependência ausente: query '{qs}' não está no arquivo nem no destino")

    slugs_var_bundle = {v["slug"] for v in bundle["variaveis"]}
    refs_var = set()
    for ind in bundle["painel"].get("indicadores", []):
        if ind.get("filtro_clique_variavel_slug"):
            refs_var.add(ind["filtro_clique_variavel_slug"])
    for pv in bundle["painel"].get("variaveis_painel", []):
        refs_var.add(pv["variavel_slug"])
    for q in bundle["queries"]:
        for p in q.get("parametros", []):
            if p.get("variavel_slug"):
                refs_var.add(p["variavel_slug"])
    for vs in sorted(refs_var):
        if vs not in slugs_var_bundle:
            existe = await query_meta("SELECT 1 FROM variaveis WHERE slug = $1", vs)
            if not existe:
                avisos.append(f"Dependência ausente: variável '{vs}' não está no arquivo nem no destino")

    return {"formato_ok": True, "plano": plano, "avisos": avisos}


# --- Task 4: importação (upsert seletivo em transação) --------------------------

async def _checar_dependencias(bundle, aplicar_var, aplicar_qry, aplicar_pnl) -> list[str]:
    """Toda query/variável referenciada pelo que vai ser aplicado tem que já
    existir no destino OU estar na lista de aplicação."""
    faltando: list[str] = []

    async def query_ok(slug):
        if slug in aplicar_qry:
            return True
        return bool(await query_meta("SELECT 1 FROM queries WHERE slug = $1", slug))

    async def var_ok(slug):
        if slug in aplicar_var:
            return True
        return bool(await query_meta("SELECT 1 FROM variaveis WHERE slug = $1", slug))

    if aplicar_pnl:
        for ind in bundle["painel"].get("indicadores", []):
            if not await query_ok(ind["query_slug"]):
                faltando.append(f"query '{ind['query_slug']}'")
            fs = ind.get("filtro_clique_variavel_slug")
            if fs and not await var_ok(fs):
                faltando.append(f"variável '{fs}'")
        for pv in bundle["painel"].get("variaveis_painel", []):
            if not await var_ok(pv["variavel_slug"]):
                faltando.append(f"variável '{pv['variavel_slug']}'")

    for q in bundle["queries"]:
        if q["slug"] not in aplicar_qry:
            continue
        if q.get("subquery_slug") and not await query_ok(q["subquery_slug"]):
            faltando.append(f"subquery '{q['subquery_slug']}'")
        if q.get("base_query_slug") and not await query_ok(q["base_query_slug"]):
            faltando.append(f"query base '{q['base_query_slug']}'")
        for p in q.get("parametros", []):
            if p.get("variavel_slug") and not await var_ok(p["variavel_slug"]):
                faltando.append(f"variável '{p['variavel_slug']}'")

    # SQL das entidades aplicadas tem que passar por validar_sql, igual ao
    # create/update de query — mantém o invariante "todo SQL gravado é válido"
    # e transforma bundle ruim em 400 (antes da transação) em vez de gravar.
    sql_erros: list[str] = []
    for q in bundle["queries"]:
        if q["slug"] not in aplicar_qry:
            continue
        try:
            validar_sql(q.get("sql_texto") or "")
        except ValueError as e:
            sql_erros.append(f"SQL inválido na query '{q['slug']}': {e}")
    for v in bundle["variaveis"]:
        if v["slug"] in aplicar_var and v.get("query_fonte"):
            try:
                validar_sql(v["query_fonte"])
            except ValueError as e:
                sql_erros.append(f"SQL inválido na variável '{v['slug']}': {e}")
    if sql_erros:
        raise HTTPException(400, "; ".join(dict.fromkeys(sql_erros)))

    # dedup preservando ordem
    return list(dict.fromkeys(faltando))


async def _upsert_variavel(conn, vb: dict):
    existente = await conn.fetch("SELECT id FROM variaveis WHERE slug = $1", vb["slug"])
    campos = ["nome", "descricao", "tipo", "query_fonte", "param_names", "ativo"]
    vals = [vb.get("nome"), vb.get("descricao"), vb.get("tipo"),
            vb.get("query_fonte"), list(vb.get("param_names") or []), vb.get("ativo", True)]
    if existente:
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(campos))
        await conn.execute(f"UPDATE variaveis SET {sets} WHERE id = ${len(campos)+1}",
                           *vals, existente[0]["id"])
    else:
        await conn.execute(
            "INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, param_names, ativo) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            vb["slug"], *vals)


async def _upsert_query_base(conn, qb: dict):
    """Passo 1: cria/atualiza a query SEM subquery_id (resolvido no passo 2)."""
    emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
    grupo_id = await resolver_grupo_id("query_grupos", qb.get("grupo_nome"), conn=conn)
    img = base64.b64decode(qb["kpi_imagem_base64"]) if qb.get("kpi_imagem_base64") else None

    dados = {c: qb.get(c) for c in QUERY_CAMPOS if c != "slug"}
    dados["empresa_id"] = emp_id
    dados["grupo_id"] = grupo_id
    dados["kpi_imagem"] = img
    dados["kpi_imagem_mime"] = qb.get("kpi_imagem_mime")

    existente = await conn.fetch(
        "SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        qb["slug"], emp_id)

    cols = list(dados.keys())
    if existente:
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        await conn.execute(f"UPDATE queries SET {sets} WHERE id = ${len(cols)+1}",
                           *[dados[c] for c in cols], existente[0]["id"])
    else:
        ph = ", ".join(f"${i+1}" for i in range(len(cols) + 1))
        await conn.execute(
            f"INSERT INTO queries (slug, {', '.join(cols)}) VALUES ({ph})",
            qb["slug"], *[dados[c] for c in cols])


async def _set_subquery(conn, slug: str, empresa_slug, subquery_slug: str, subquery_empresa_slug):
    """Passo 2: liga a query pai (slug, empresa) à sua subquery. Ambos os
    statements são escopados por (slug, empresa_id IS NOT DISTINCT FROM ...),
    igual a `_id_query_por_slug` — nunca por slug sozinho, senão um slug
    repetido entre empresas resolveria/gravaria na linha errada."""
    emp_id = await _empresa_id_de_slug(empresa_slug)
    sub_emp_id = await _empresa_id_de_slug(subquery_empresa_slug)
    sub = await conn.fetch(
        "SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        subquery_slug, sub_emp_id)
    sub_id = sub[0]["id"] if sub else None
    await conn.execute(
        "UPDATE queries SET subquery_id = $1 WHERE slug = $2 AND empresa_id IS NOT DISTINCT FROM $3",
        sub_id, slug, emp_id)


async def _set_query_base(conn, slug: str, empresa_slug, base_slug: str, base_empresa_slug):
    """Mesmo padrão de `_set_subquery`, pro vínculo query_base_id."""
    emp_id = await _empresa_id_de_slug(empresa_slug)
    base_emp_id = await _empresa_id_de_slug(base_empresa_slug)
    base = await conn.fetch(
        "SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        base_slug, base_emp_id)
    base_id = base[0]["id"] if base else None
    await conn.execute(
        "UPDATE queries SET query_base_id = $1 WHERE slug = $2 AND empresa_id IS NOT DISTINCT FROM $3",
        base_id, slug, emp_id)


async def _id_query_por_slug(conn, slug: str, emp_slug):
    emp_id = await _empresa_id_de_slug(emp_slug)
    r = await conn.fetch("SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
                         slug, emp_id)
    return r[0]["id"] if r else None


async def _id_var_por_slug(conn, slug):
    if not slug:
        return None
    r = await conn.fetch("SELECT id FROM variaveis WHERE slug = $1", slug)
    return r[0]["id"] if r else None


async def _reinserir_filhas_query(conn, qb: dict):
    qid = await _id_query_por_slug(conn, qb["slug"], qb.get("empresa_slug"))
    for tabela in ("query_parametros", "query_agrupamentos", "query_agregacoes", "query_subquery_parametros"):
        await conn.execute(f"DELETE FROM {tabela} WHERE query_id = $1", qid)

    for p in qb.get("parametros", []):
        await conn.execute(
            "INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            qid, p["nome"], p.get("tipo", "text"), p.get("obrigatorio", False),
            p.get("valor_padrao"), p.get("descricao"),
            await _id_var_por_slug(conn, p.get("variavel_slug")), p.get("param_slot"))
    for a in qb.get("agrupamentos", []):
        await conn.execute("INSERT INTO query_agrupamentos (query_id, coluna, ordem) VALUES ($1,$2,$3)",
                           qid, a["coluna"], a.get("ordem", 0))
    for a in qb.get("agregacoes", []):
        await conn.execute("INSERT INTO query_agregacoes (query_id, coluna, funcao, label, ordem) VALUES ($1,$2,$3,$4,$5)",
                           qid, a["coluna"], a["funcao"], a.get("label"), a.get("ordem", 0))
    for s in qb.get("subquery_parametros", []):
        await conn.execute(
            "INSERT INTO query_subquery_parametros (query_id, coluna_origem, parametro_destino, ordem) VALUES ($1,$2,$3,$4)",
            qid, s["coluna_origem"], s["parametro_destino"], s.get("ordem", 0))


async def _upsert_painel(conn, pb: dict, avisos: list | None = None):
    if avisos is None:
        avisos = []
    emp_id = await _empresa_id_de_slug(pb.get("empresa_slug"))
    if pb.get("empresa_slug") and emp_id is None:
        avisos.append(
            f"Empresa '{pb['empresa_slug']}' não existe no destino — "
            f"painel '{pb['slug']}' importada como global")
    grupo_id = await resolver_grupo_id("painel_grupos", pb.get("grupo_nome"), conn=conn)
    img = base64.b64decode(pb["imagem_base64"]) if pb.get("imagem_base64") else None

    dados = {c: pb.get(c) for c in PAINEL_CAMPOS if c != "slug"}
    dados["empresa_id"] = emp_id
    dados["grupo_id"] = grupo_id
    dados["imagem"] = img
    dados["imagem_mime"] = pb.get("imagem_mime")
    cols = list(dados.keys())

    existente = await conn.fetch("SELECT id FROM paineis WHERE slug = $1", pb["slug"])
    if existente:
        pid = existente[0]["id"]
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        await conn.execute(f"UPDATE paineis SET {sets} WHERE id = ${len(cols)+1}",
                           *[dados[c] for c in cols], pid)
    else:
        ph = ", ".join(f"${i+1}" for i in range(len(cols) + 1))
        row = await conn.fetch(
            f"INSERT INTO paineis (slug, {', '.join(cols)}) VALUES ({ph}) RETURNING id",
            pb["slug"], *[dados[c] for c in cols])
        pid = row[0]["id"]

    await conn.execute("DELETE FROM painel_indicadores WHERE painel_id = $1", pid)
    for ind in pb.get("indicadores", []):
        fcv_slug = ind.get("filtro_clique_variavel_slug")
        fcv_id = await _id_var_por_slug(conn, fcv_slug)
        if fcv_slug and fcv_id is None:
            avisos.append(
                f"Filtro-por-clique '{fcv_slug}' do indicador não encontrado — ignorado")
        await conn.execute(
            "INSERT INTO painel_indicadores "
            "(painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, filtro_clique_variavel_id) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            pid, ind["query_slug"], ind.get("titulo"), ind["linha"], ind["coluna"],
            ind.get("col_span", 1), ind.get("row_span", 1), ind.get("posicao", 0),
            fcv_id)

    await conn.execute("DELETE FROM painel_variaveis WHERE painel_id = $1", pid)
    for pv in pb.get("variaveis_painel", []):
        vid = await _id_var_por_slug(conn, pv["variavel_slug"])
        if vid is None:
            avisos.append(
                f"Variável de painel '{pv['variavel_slug']}' não encontrada — filtro ignorado")
            continue
        await conn.execute(
            "INSERT INTO painel_variaveis "
            "(painel_id, variavel_id, obrigatorio, valor_padrao, valor_padrao_inicio, valor_padrao_fim, posicao) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            pid, vid, pv.get("obrigatorio", False), pv.get("valor_padrao"),
            pv.get("valor_padrao_inicio"), pv.get("valor_padrao_fim"), pv.get("posicao", 0))


async def importar_bundle(bundle: dict, aplicar: dict) -> dict:
    validar_formato(bundle)
    aplicar_var = set(aplicar.get("variaveis", []))
    aplicar_qry = set(aplicar.get("queries", []))
    aplicar_pnl = bool(aplicar.get("painel"))

    faltando = await _checar_dependencias(bundle, aplicar_var, aplicar_qry, aplicar_pnl)
    if faltando:
        raise HTTPException(400, "Dependências ausentes (marque para importar): " + ", ".join(faltando))

    por_slug = {q["slug"]: q for q in bundle["queries"]}
    slugs_query_tocados: list[str] = []
    avisos: list[str] = []
    async with meta_tx() as conn:
        for vb in bundle["variaveis"]:
            if vb["slug"] in aplicar_var:
                await _upsert_variavel(conn, vb)

        for qb in bundle["queries"]:
            if qb["slug"] in aplicar_qry:
                await _upsert_query_base(conn, qb)
                slugs_query_tocados.append(qb["slug"])
                emp_slug = qb.get("empresa_slug")
                if emp_slug and await _empresa_id_de_slug(emp_slug) is None:
                    avisos.append(
                        f"Empresa '{emp_slug}' não existe no destino — "
                        f"query '{qb['slug']}' importada como global")

        for qb in bundle["queries"]:
            if qb["slug"] not in aplicar_qry:
                continue
            if qb.get("subquery_slug"):
                sub_entry = por_slug.get(qb["subquery_slug"])
                sub_emp_slug = sub_entry.get("empresa_slug") if sub_entry else qb.get("empresa_slug")
                await _set_subquery(conn, qb["slug"], qb.get("empresa_slug"),
                                    qb["subquery_slug"], sub_emp_slug)
            else:
                # origem removeu a subquery — zera o id obsoleto no destino,
                # senão vira conflito fantasma permanente em subquery_slug
                emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
                await conn.execute(
                    "UPDATE queries SET subquery_id = NULL "
                    "WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
                    qb["slug"], emp_id)

        for qb in bundle["queries"]:
            if qb["slug"] not in aplicar_qry:
                continue
            if qb.get("base_query_slug"):
                base_entry = por_slug.get(qb["base_query_slug"])
                base_emp_slug = base_entry.get("empresa_slug") if base_entry else qb.get("empresa_slug")
                await _set_query_base(conn, qb["slug"], qb.get("empresa_slug"),
                                      qb["base_query_slug"], base_emp_slug)
            else:
                emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
                await conn.execute(
                    "UPDATE queries SET query_base_id = NULL "
                    "WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
                    qb["slug"], emp_id)

        for qb in bundle["queries"]:
            if qb["slug"] in aplicar_qry:
                await _reinserir_filhas_query(conn, qb)

        if aplicar_pnl:
            await _upsert_painel(conn, bundle["painel"], avisos)

    for slug in slugs_query_tocados:
        await invalidar_cache_query(slug)

    return {
        "painel_slug": bundle["painel"]["slug"],
        "aplicado": {"variaveis": len(aplicar_var), "queries": len(aplicar_qry), "painel": aplicar_pnl},
        "avisos": list(dict.fromkeys(avisos)),
    }
