TABLE_DYNAMIC_SQL = "SELECT 'Fazenda Manga' AS fazenda, 'Equipamento 1' AS equipamento, 3 AS qtd"


def _criar_query_table_dynamic(client, auth_token, slug, subquery_id=None):
    res = client.post(
        "/api/queries/",
        json={
            "slug": slug,
            "nome": "Teste Table Dynamic",
            "sql_texto": TABLE_DYNAMIC_SQL,
            "tipo": "table_dynamic",
            "subquery_id": subquery_id,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    return res.json()


def test_criar_query_table_dynamic(client, auth_token):
    body = _criar_query_table_dynamic(client, auth_token, "teste_table_dynamic_criar")
    assert body["tipo"] == "table_dynamic"
    assert body["subquery_id"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_tipo_invalido_ainda_rejeitado(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_tipo_invalido",
            "nome": "Teste",
            "sql_texto": TABLE_DYNAMIC_SQL,
            "tipo": "nao_existe",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_agrupamentos_get_put_roundtrip(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agrupamentos")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agrupamentos",
            json=[
                {"coluna": "fazenda", "ordem": 0},
                {"coluna": "equipamento", "ordem": 1},
            ],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert [r["coluna"] for r in salvos] == ["fazenda", "equipamento"]

        get_res = client.get(
            f"/api/queries/{query['id']}/agrupamentos",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert [r["coluna"] for r in get_res.json()] == ["fazenda", "equipamento"]
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_agregacoes_get_put_roundtrip(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agregacoes")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agregacoes",
            json=[{"coluna": "qtd", "funcao": "soma", "label": "Total", "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert salvos[0]["coluna"] == "qtd"
        assert salvos[0]["funcao"] == "soma"
        assert salvos[0]["label"] == "Total"
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_agregacoes_funcao_invalida_rejeitada(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agregacoes_invalida")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agregacoes",
            json=[{"coluna": "qtd", "funcao": "mediana", "label": None, "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 400
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_subquery_parametros_get_put_roundtrip(client, auth_token):
    sub = client.post(
        "/api/queries/",
        json={
            "slug": "teste_subquery_alvo",
            "nome": "Subconsulta",
            "sql_texto": "SELECT 1 AS valor",
            "tipo": "kpi",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()
    query = _criar_query_table_dynamic(client, auth_token, "teste_subquery_parametros", subquery_id=sub["id"])
    try:
        res = client.put(
            f"/api/queries/{query['id']}/subquery-parametros",
            json=[{"coluna_origem": "equipamento", "parametro_destino": "prefixo", "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert salvos[0]["coluna_origem"] == "equipamento"
        assert salvos[0]["parametro_destino"] == "prefixo"

        atualizada = client.get(
            f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"}
        ).json()
        assert atualizada["subquery_id"] == sub["id"]
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        client.delete(f"/api/queries/{sub['id']}", headers={"Authorization": f"Bearer {auth_token}"})
