KPI_SQL = "SELECT 'Receita' AS label, 1234 AS valor"


def test_criar_query_kpi_valor_primeiro(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_kpi_valor_primeiro",
            "nome": "Teste Valor Primeiro",
            "sql_texto": KPI_SQL,
            "tipo": "kpi",
            "kpi_valor_primeiro": True,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["kpi_valor_primeiro"] is True
    client.delete(
        f"/api/queries/{res.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_kpi_sem_valor_primeiro_fica_false(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_kpi_valor_primeiro_default",
            "nome": "Teste Valor Primeiro Default",
            "sql_texto": KPI_SQL,
            "tipo": "kpi",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["kpi_valor_primeiro"] is False
    client.delete(
        f"/api/queries/{res.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_atualizar_query_kpi_valor_primeiro(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_kpi_valor_primeiro_update",
            "nome": "Teste",
            "sql_texto": KPI_SQL,
            "tipo": "kpi",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={"kpi_valor_primeiro": True},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["kpi_valor_primeiro"] is True

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
