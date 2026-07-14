def test_gerar_sso_api_key_retorna_texto_puro_uma_vez(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        f"/api/empresas/{alpha['id']}/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "api_key" in body
    assert len(body["api_key"]) > 20


def test_gerar_sso_api_key_empresa_inexistente_retorna_404(client, auth_token):
    res = client.post(
        "/api/empresas/999999/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 404


def test_gerar_sso_api_key_sem_autenticacao_retorna_403(client):
    res = client.post("/api/empresas/1/sso-api-key")
    assert res.status_code == 403


def test_testar_sso_acesso_com_query_valida_devolve_slugs(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT painel_slug FROM (VALUES ('teste_a', 'painel_x'), ('teste_a', 'painel_y')) AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert sorted(body["slugs"]) == ["painel_x", "painel_y"]


def test_testar_sso_acesso_sem_coluna_painel_slug_retorna_erro_claro(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT 1 AS id, 'x' AS nome, $1::text AS ignorar",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "painel_slug" in body["erro"]


def test_testar_sso_acesso_com_sql_invalido_retorna_erro_sem_500(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT * FROM tabela_que_nao_existe",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["erro"]


def test_testar_sso_acesso_empresa_invalida_retorna_erro_sem_500(client, auth_token):
    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": 999999,
            "query": "SELECT painel_slug FROM (VALUES ('a', 'b')) AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False


def test_patch_empresa_com_sso_query_acesso_sql_proibido_retorna_400(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")
    empresa_atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()

    res = client.patch(
        f"/api/empresas/{alpha['id']}",
        json={
            "slug": empresa_atual["slug"],
            "nome": empresa_atual["nome"],
            "db_host": empresa_atual["db_host"],
            "db_port": empresa_atual["db_port"],
            "db_name": empresa_atual["db_name"],
            "db_user": empresa_atual["db_user"],
            "ativo": empresa_atual["ativo"],
            "sso_query_acesso": "DROP TABLE empresas",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_testar_sso_acesso_com_sql_proibido_retorna_erro_sem_500(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "DROP TABLE empresas",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
