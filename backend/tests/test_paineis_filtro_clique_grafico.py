import uuid
from conftest import hard_delete_painel, hard_delete_variavel


def test_renderizar_painel_anexa_filtro_clique_configurado(client, auth_token):
    var_slug = f"var_filtro_clique_{uuid.uuid4().hex[:8]}"
    variavel = client.post(
        "/api/variaveis/",
        json={
            "slug": var_slug,
            "nome": "Categoria Teste",
            "tipo": "multiselect",
            "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_filtro_clique_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Filtro Clique",
            "sql_texto": "SELECT 'A' AS label, 10 AS valor, 1 AS categoria_id",
            "tipo": "chart_bar",
            "cache_ttl": 0,
            "chart_filtro_coluna": "categoria_id",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_filtro_clique_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Filtro Clique"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]

    client.put(
        f"/api/paineis/{painel_id}/variaveis",
        json=[{"variavel_id": variavel["id"]}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{
            "query_slug": query_slug, "linha": 1, "coluna": 1,
            "filtro_clique_variavel_id": variavel["id"],
        }],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        ind = res.json()["indicadores"][0]
        assert ind["chart_filtro_coluna"] == "categoria_id"
        assert ind["filtro_clique_variavel_id"] == variavel["id"]
        assert ind["filtro_clique_variavel_slug"] == var_slug
        assert ind["filtro_clique_variavel_tipo"] == "multiselect"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        hard_delete_variavel(variavel["id"])


def test_renderizar_painel_sem_filtro_clique_configurado_retorna_none(client, auth_token):
    query_slug = f"query_sem_filtro_clique_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Sem Filtro Clique",
            "sql_texto": "SELECT 'A' AS label, 10 AS valor",
            "tipo": "chart_bar",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_sem_filtro_clique_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Sem Filtro Clique"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        ind = res.json()["indicadores"][0]
        assert ind["chart_filtro_coluna"] is None
        assert ind["filtro_clique_variavel_id"] is None
        assert ind["filtro_clique_variavel_slug"] is None
        assert ind["filtro_clique_variavel_tipo"] is None
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_adicionar_indicador_com_filtro_clique_variavel_id(client, auth_token):
    var_slug = f"var_ind_filtro_{uuid.uuid4().hex[:8]}"
    variavel = client.post(
        "/api/variaveis/",
        json={
            "slug": var_slug, "nome": "Var Indicador", "tipo": "select",
            "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_ind_filtro_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug, "nome": "Query Ind Filtro",
            "sql_texto": "SELECT 'A' AS label, 1 AS valor", "tipo": "chart_bar", "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_ind_filtro_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Ind Filtro"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]

    try:
        res = client.post(
            f"/api/paineis/{painel_id}/indicadores",
            json={
                "query_slug": query_slug, "linha": 1, "coluna": 1,
                "filtro_clique_variavel_id": variavel["id"],
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        assert res.json()["filtro_clique_variavel_id"] == variavel["id"]
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        hard_delete_variavel(variavel["id"])
