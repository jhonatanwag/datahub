CHART_SQL = "SELECT 'A' AS label, 10 AS valor"


def test_criar_query_chart_com_valor_label(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_chart_valor_label",
            "nome": "Teste Valor Label",
            "sql_texto": CHART_SQL,
            "tipo": "chart_bar",
            "chart_valor_label": "Perdas",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["chart_valor_label"] == "Perdas"
    client.delete(
        f"/api/queries/{res.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_sem_valor_label_fica_nulo(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_chart_valor_label_default",
            "nome": "Teste Valor Label Default",
            "sql_texto": CHART_SQL,
            "tipo": "chart_bar",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["chart_valor_label"] is None
    client.delete(
        f"/api/queries/{res.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_atualizar_query_chart_valor_label(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_chart_valor_label_update",
            "nome": "Teste",
            "sql_texto": CHART_SQL,
            "tipo": "chart_bar",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={"chart_valor_label": "Pendências"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json()["chart_valor_label"] == "Pendências"

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
