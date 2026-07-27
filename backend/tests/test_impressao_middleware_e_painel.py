import uuid
from conftest import hard_delete_painel


def test_me_inclui_url_impressao_base_da_empresa_ativa(client, auth_token):
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
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": "https://www.psosistemas.com.br:8443/Alpha/"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        assert res.json()["url_impressao_base"] == "https://www.psosistemas.com.br:8443/Alpha/"
    finally:
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": atual.get("url_impressao_base")},
            headers={"Authorization": f"Bearer {auth_token}"},
        )


def test_renderizar_painel_inclui_campos_de_impressao_do_indicador(client, auth_token):
    query_slug = f"query_impressao_painel_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Impressão Painel",
            "sql_texto": "SELECT '1642d8a9-a204-4745-b446-64232422a886' AS uuid, 'Item A' AS descricao",
            "tipo": "table",
            "cache_ttl": 0,
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    painel_slug = f"painel_impressao_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Impressão"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert painel_res.status_code == 200
    painel_id = painel_res.json()["id"]

    ind_res = client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ind_res.status_code == 200

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        indicador = res.json()["indicadores"][0]
        assert indicador["impressao_habilitada"] is True
        assert indicador["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
        assert indicador["impressao_coluna"] == "uuid"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
