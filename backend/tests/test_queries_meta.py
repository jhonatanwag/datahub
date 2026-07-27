TABLE_SQL = "SELECT 50 AS valor, 10 AS meta_inicio, 100 AS meta_fim"


def test_criar_query_table_com_meta_habilitada(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_habilitada",
            "nome": "Teste Meta",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
            "meta_cor_dentro": "#00ff00",
            "meta_cor_fora": "#ff0000",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is True
    assert body["meta_coluna_valor"] == "valor"
    assert body["meta_coluna_inicio"] == "meta_inicio"
    assert body["meta_coluna_fim"] == "meta_fim"
    assert body["meta_cor_dentro"] == "#00ff00"
    assert body["meta_cor_fora"] == "#ff0000"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_table_sem_meta_fica_com_defaults(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_default",
            "nome": "Teste Meta Default",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is False
    assert body["meta_coluna_valor"] is None
    assert body["meta_coluna_inicio"] is None
    assert body["meta_coluna_fim"] is None
    assert body["meta_cor_dentro"] == "#3fb950"
    assert body["meta_cor_fora"] == "#f85149"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_campos_de_meta(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_update",
            "nome": "Teste",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is True
    assert body["meta_coluna_valor"] == "valor"
    assert body["meta_coluna_inicio"] == "meta_inicio"
    assert body["meta_coluna_fim"] == "meta_fim"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
