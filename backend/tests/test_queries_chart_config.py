CHART_SQL = "SELECT 'A' AS label, 10 AS valor UNION ALL SELECT 'B', 20"


def _criar_query_chart(client, auth_token, slug, **overrides):
    body = {
        "slug": slug,
        "nome": "Teste Config Grafico",
        "sql_texto": CHART_SQL,
        "tipo": "chart_bar",
        **overrides,
    }
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_usa_defaults(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_chart_config_default")
    assert res.status_code == 200
    body = res.json()
    assert body["chart_fonte_tamanho"] == 12
    assert body["chart_truncar_label"] is False
    assert body["chart_truncar_tamanho"] == 15
    assert body["chart_mostrar_valor"] is False
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_com_valores_customizados(client, auth_token):
    res = _criar_query_chart(
        client, auth_token, "teste_chart_config_custom",
        chart_fonte_tamanho=18,
        chart_truncar_label=True,
        chart_truncar_tamanho=8,
        chart_mostrar_valor=True,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["chart_fonte_tamanho"] == 18
    assert body["chart_truncar_label"] is True
    assert body["chart_truncar_tamanho"] == 8
    assert body["chart_mostrar_valor"] is True
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_atualizar_query_chart_config(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_chart_config_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"chart_fonte_tamanho": 20, "chart_mostrar_valor": True},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    body = patch_res.json()
    assert body["chart_fonte_tamanho"] == 20
    assert body["chart_mostrar_valor"] is True
    # campos não enviados no PATCH permanecem com o valor anterior (defaults)
    assert body["chart_truncar_tamanho"] == 15

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
