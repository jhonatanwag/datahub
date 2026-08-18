def test_executar_query_com_parametro_na_querystring_filtra_resultado(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_executar_parametrizada",
            "nome": "Teste Executar Parametrizada",
            "sql_texto": "SELECT $1::text AS valor_recebido",
            "tipo": "kpi",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]
    client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "meu_param", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            "/api/queries/executar/teste_executar_parametrizada?meu_param=abc123",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        assert res.json()["data"][0]["valor_recebido"] == "abc123"

        sem_param = client.get(
            "/api/queries/executar/teste_executar_parametrizada",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert sem_param.status_code == 200
        assert sem_param.json()["data"][0]["valor_recebido"] is None
    finally:
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
