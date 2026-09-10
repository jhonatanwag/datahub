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
