TABLE_SQL = "SELECT '1642d8a9-a204-4745-b446-64232422a886' AS uuid, 'Item A' AS descricao"


def test_criar_query_table_com_impressao_habilitada(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_habilitada",
            "nome": "Teste Impressão",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is True
    assert body["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
    assert body["impressao_coluna"] == "uuid"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_table_sem_impressao_fica_desabilitada_por_padrao(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_default",
            "nome": "Teste Impressão Default",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is False
    assert body["impressao_caminho"] is None
    assert body["impressao_coluna"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_campos_de_impressao(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_update",
            "nome": "Teste",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is True
    assert body["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
    assert body["impressao_coluna"] == "uuid"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
