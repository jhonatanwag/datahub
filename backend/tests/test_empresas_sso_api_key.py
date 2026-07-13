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
