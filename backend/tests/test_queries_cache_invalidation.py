def test_editar_sql_de_query_global_invalida_cache(client, auth_token):
    """Query global (sem empresa_id) é a mais comum no dashboard — o cache é
    chaveado por slug+empresa, então editar o SQL precisa invalidar em todas
    as empresas, não só quando a query tem empresa_id definido."""
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_cache_invalidation",
            "nome": "Teste Cache Invalidation",
            "sql_texto": "SELECT 'A' AS label, 10 AS valor, 20 AS valor2",
            "tipo": "chart_bar",
            "cache_ttl": 300,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    primeira = client.get(
        "/api/queries/executar/teste_cache_invalidation",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert primeira.status_code == 200
    assert primeira.json()["from_cache"] is False
    assert primeira.json()["data"][0]["valor2"] == 20

    client.patch(
        f"/api/queries/{query_id}",
        json={"sql_texto": "SELECT 'A' AS label, 10 AS valor, 99 AS media_pendencia"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    segunda = client.get(
        "/api/queries/executar/teste_cache_invalidation",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert segunda.status_code == 200
    assert segunda.json()["from_cache"] is False
    assert "media_pendencia" in segunda.json()["data"][0]
    assert "valor2" not in segunda.json()["data"][0]

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
