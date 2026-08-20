CHART_SQL = "SELECT 'A' AS label, 10 AS valor, 1 AS categoria_id UNION ALL SELECT 'B', 20, 2"


def _criar_query_chart(client, auth_token, slug, **overrides):
    body = {
        "slug": slug,
        "nome": "Teste Filtro Clique",
        "sql_texto": CHART_SQL,
        "tipo": "chart_bar",
        **overrides,
    }
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_sem_filtro_coluna_por_padrao(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_filtro_clique_default")
    assert res.status_code == 200
    body = res.json()
    assert body["chart_filtro_coluna"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_chart_com_filtro_coluna(client, auth_token):
    res = _criar_query_chart(
        client, auth_token, "teste_filtro_clique_custom",
        chart_filtro_coluna="categoria_id",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["chart_filtro_coluna"] == "categoria_id"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_chart_filtro_coluna(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_filtro_clique_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"chart_filtro_coluna": "categoria_id"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["chart_filtro_coluna"] == "categoria_id"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
