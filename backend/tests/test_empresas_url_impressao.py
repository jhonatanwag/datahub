def test_atualizar_empresa_com_url_impressao_base_persiste_e_devolve(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")
    atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()

    payload_base = {
        "slug": atual["slug"], "nome": atual["nome"], "db_host": atual["db_host"],
        "db_port": atual["db_port"], "db_name": atual["db_name"], "db_user": atual["db_user"],
        "ativo": atual["ativo"],
    }

    try:
        res = client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": "https://www.psosistemas.com.br:8443/Alpha/"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200

        verificar = client.get(
            f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
        ).json()
        assert verificar["url_impressao_base"] == "https://www.psosistemas.com.br:8443/Alpha/"
    finally:
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": atual.get("url_impressao_base")},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
