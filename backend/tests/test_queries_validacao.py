def test_criar_query_com_slug_vazio_retorna_400(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={"slug": "", "nome": "Teste", "sql_texto": "SELECT 1", "tipo": "table"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_criar_query_com_nome_vazio_retorna_400(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={"slug": "teste_nome_vazio", "nome": "", "sql_texto": "SELECT 1", "tipo": "table"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_criar_query_com_slug_so_espacos_retorna_400(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={"slug": "   ", "nome": "   ", "sql_texto": "SELECT 1", "tipo": "table"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_atualizar_query_com_nome_vazio_retorna_400(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={"slug": "teste_patch_nome_vazio", "nome": "Nome Valido", "sql_texto": "SELECT 1", "tipo": "table"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={"nome": ""},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
