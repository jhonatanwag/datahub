import uuid
import pytest
from conftest import _connect_meta
from conftest import hard_delete_painel, hard_delete_variavel
import asyncio

from services.grupos import resolver_grupo_id


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _criar_query(client, token, **over):
    slug = over.pop("slug", f"q_{uuid.uuid4().hex[:8]}")
    body = {
        "slug": slug, "nome": over.pop("nome", "Q"),
        "sql_texto": over.pop("sql_texto", "SELECT 1 AS valor"),
        "tipo": over.pop("tipo", "kpi"), "cache_ttl": 0,
    }
    body.update(over)
    r = client.post("/api/queries/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _criar_variavel(client, token, **over):
    slug = over.pop("slug", f"v_{uuid.uuid4().hex[:8]}")
    body = {"slug": slug, "nome": "V", "tipo": "text"}
    body.update(over)
    r = client.post("/api/variaveis/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _criar_painel(client, token, **over):
    slug = over.pop("slug", f"p_{uuid.uuid4().hex[:8]}")
    body = {"slug": slug, "nome": "P"}
    body.update(over)
    r = client.post("/api/paineis/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_resolver_grupo_id_acha_ou_cria_e_reusa():
    nome = f"Grupo Teste {uuid.uuid4().hex[:8]}"

    async def cenario():
        conn = await _connect_meta()
        id1 = None
        try:
            id1 = await resolver_grupo_id("painel_grupos", nome, conn=conn)
            id2 = await resolver_grupo_id("painel_grupos", nome.upper(), conn=conn)  # case-insensitive
            vazio = await resolver_grupo_id("painel_grupos", "  ", conn=conn)

            assert id1 is not None
            assert id1 == id2
            assert vazio is None
        finally:
            if id1:
                await conn.execute("DELETE FROM painel_grupos WHERE id = $1", id1)
            await conn.close()

    asyncio.run(cenario())


def test_resolver_grupo_id_rejeita_tabela_desconhecida():
    async def cenario():
        with pytest.raises(ValueError):
            await resolver_grupo_id("usuarios", "x")
    asyncio.run(cenario())


def test_exportar_traz_fecho_transitivo_de_subquery_e_variaveis(client, auth_token):
    t = auth_token
    var = _criar_variavel(client, t, tipo="text")
    sub = _criar_query(client, t, tipo="table", sql_texto="SELECT 2 AS valor")
    principal = _criar_query(client, t, tipo="table", subquery_id=sub["id"])
    # parâmetro da principal ligado à variável
    client.put(f"/api/queries/{principal['id']}/parametros",
               json=[{"nome": "p1", "tipo": "text", "variavel_id": var["id"]}],
               headers=_headers(t))
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": principal["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))

    try:
        r = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t))
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        b = r.json()
        assert b["formato"] == "datahub-painel"
        assert b["versao"] == 1
        query_slugs = {q["slug"] for q in b["queries"]}
        assert principal["slug"] in query_slugs
        assert sub["slug"] in query_slugs          # fecho transitivo
        assert {v["slug"] for v in b["variaveis"]} == {var["slug"]}
        pq = next(q for q in b["queries"] if q["slug"] == principal["slug"])
        assert pq["subquery_slug"] == sub["slug"]
        assert pq["parametros"][0]["variavel_slug"] == var["slug"]
        assert b["painel"]["indicadores"][0]["query_slug"] == principal["slug"]
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{principal['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{sub['id']}", headers=_headers(t))
        hard_delete_variavel(var["id"])


def test_exportar_avisa_indicador_com_query_inexistente(client, auth_token):
    t = auth_token
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": "nao_existe_xyz", "linha": 1, "coluna": 1}],
               headers=_headers(t))
    try:
        r = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t))
        assert r.status_code == 200, r.text
        b = r.json()
        assert any("nao_existe_xyz" in a for a in b["avisos"])
        assert b["queries"] == []
    finally:
        hard_delete_painel(painel["id"])


def _exportar(client, token, painel_id):
    r = client.get(f"/api/paineis/{painel_id}/exportar", headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_analisar_classifica_novo_identico_e_conflito(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS valor")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    try:
        # tudo já existe e nada mudou -> identico
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        assert r.status_code == 200, r.text
        plano = r.json()["plano"]
        assert plano["painel"]["situacao"] == "identico"
        assert plano["queries"][0]["situacao"] == "identico"

        # mexe no sql_texto do bundle -> conflito em sql_texto
        bundle["queries"][0]["sql_texto"] = "SELECT 999 AS valor"
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        item = r.json()["plano"]["queries"][0]
        assert item["situacao"] == "conflito"
        assert "sql_texto" in item["campos_diferentes"]

        # slug de query inexistente -> novo
        bundle["queries"][0]["slug"] = "totalmente_nova_xyz"
        bundle["painel"]["indicadores"][0]["query_slug"] = "totalmente_nova_xyz"
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        assert r.json()["plano"]["queries"][0]["situacao"] == "novo"
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{q['id']}", headers=_headers(t))


def test_analisar_rejeita_formato_invalido(client, auth_token):
    r = client.post("/api/portabilidade/paineis/analisar",
                    json={"formato": "outra-coisa"}, headers=_headers(auth_token))
    assert r.status_code == 400


# --- Task 4: importação (upsert seletivo em transação) --------------------------

def _analisar(client, token, bundle):
    r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _importar(client, token, bundle, aplicar):
    return client.post("/api/portabilidade/paineis/importar",
                       json={"bundle": bundle, "aplicar": aplicar}, headers=_headers(token))


def test_importar_respeita_lista_aplicar_e_cria_so_o_marcado(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    # apaga tudo do destino
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))

    novo_painel_id = None
    try:
        # aplicar só a query, não o painel
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        assert r.json()["aplicado"]["queries"] == 1
        criada = client.get("/api/queries/", headers=_headers(t)).json()
        assert any(x["slug"] == q["slug"] for x in criada)

        # agora aplicar o painel também
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": True})
        assert r.status_code == 200, r.text
        pl = client.get("/api/paineis/", headers=_headers(t)).json()
        alvo = next(x for x in pl if x["slug"] == bundle["painel"]["slug"])
        novo_painel_id = alvo["id"]
        inds = client.get(f"/api/paineis/{novo_painel_id}/indicadores", headers=_headers(t)).json()
        assert inds[0]["query_slug"] == q["slug"]
    finally:
        if novo_painel_id:
            hard_delete_painel(novo_painel_id)
        nova = client.get("/api/queries/", headers=_headers(t)).json()
        alvo = next((x for x in nova if x["slug"] == q["slug"]), None)
        if alvo:
            client.delete(f"/api/queries/{alvo['id']}", headers=_headers(t))


def test_importar_bloqueia_quando_dependencia_ausente(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))

    try:
        # aplicar o painel mas NÃO a query da qual ele depende, e a query não existe no destino
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [], "painel": True})
        assert r.status_code == 400
        assert q["slug"] in r.text
    finally:
        pl = client.get("/api/paineis/", headers=_headers(t)).json()
        alvo = next((x for x in pl if x["slug"] == bundle["painel"]["slug"]), None)
        if alvo:
            hard_delete_painel(alvo["id"])


def test_importar_sobrescreve_query_existente_com_conteudo_do_bundle(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS valor")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    try:
        # edita a query no destino
        client.patch(f"/api/queries/{q['id']}", json={"sql_texto": "SELECT 42 AS valor"}, headers=_headers(t))
        # reimporta o bundle original marcando a query
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        atual = client.get(f"/api/queries/{q['id']}", headers=_headers(t)).json()
        assert atual["sql_texto"] == "SELECT 1 AS valor"
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{q['id']}", headers=_headers(t))


def test_importar_recursao_de_subquery_mutua(client, auth_token):
    t = auth_token
    a = _criar_query(client, t, tipo="table")
    b = _criar_query(client, t, tipo="table")
    client.patch(f"/api/queries/{a['id']}", json={"subquery_id": b["id"]}, headers=_headers(t))
    client.patch(f"/api/queries/{b['id']}", json={"subquery_id": a["id"]}, headers=_headers(t))
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": a["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{a['id']}", headers=_headers(t))
    client.delete(f"/api/queries/{b['id']}", headers=_headers(t))

    ids = []
    try:
        r = _importar(client, t, bundle,
                      {"variaveis": [], "queries": [a["slug"], b["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        todas = client.get("/api/queries/", headers=_headers(t)).json()
        qa = next(x for x in todas if x["slug"] == a["slug"])
        qb = next(x for x in todas if x["slug"] == b["slug"])
        ids = [qa["id"], qb["id"]]
        assert qa["subquery_id"] == qb["id"]
        assert qb["subquery_id"] == qa["id"]
    finally:
        # quebra o ciclo antes de deletar
        for i in ids:
            client.patch(f"/api/queries/{i}", json={"subquery_id": None}, headers=_headers(t))
        for i in ids:
            client.delete(f"/api/queries/{i}", headers=_headers(t))


def test_importar_faz_rollback_quando_painel_falha(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS valor")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))

    # força estouro de VARCHAR(100) no slug do painel — a query é gravada antes
    # do painel na MESMA transação; se o rollback funcionar, a query some junto.
    bundle["painel"]["slug"] = "x" * 120

    try:
        with pytest.raises(Exception):
            _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": True})
        nova = client.get("/api/queries/", headers=_headers(t)).json()
        assert not any(x["slug"] == q["slug"] for x in nova), "rollback falhou: query foi gravada"
    finally:
        nova = client.get("/api/queries/", headers=_headers(t)).json()
        alvo = next((x for x in nova if x["slug"] == q["slug"]), None)
        if alvo:
            client.delete(f"/api/queries/{alvo['id']}", headers=_headers(t))
        pl = client.get("/api/paineis/", headers=_headers(t)).json()
        alvo = next((x for x in pl if x["slug"] == bundle["painel"]["slug"]), None)
        if alvo:
            hard_delete_painel(alvo["id"])
