import uuid
from conftest import hard_delete_painel


def test_renderizar_painel_anexa_config_de_table_dynamic(client, auth_token):
    sub_slug = f"sub_{uuid.uuid4().hex[:8]}"
    sub = client.post(
        "/api/queries/",
        json={
            "slug": sub_slug,
            "nome": "Subconsulta KPI",
            "sql_texto": "SELECT 1 AS valor",
            "tipo": "kpi",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_dynamic_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Dynamic",
            "sql_texto": "SELECT 'Fazenda Manga' AS fazenda, 'Equip 1' AS equipamento, 3 AS qtd",
            "tipo": "table_dynamic",
            "cache_ttl": 0,
            "subquery_id": sub["id"],
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    client.put(
        f"/api/queries/{query['id']}/agrupamentos",
        json=[{"coluna": "fazenda", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/queries/{query['id']}/agregacoes",
        json=[{"coluna": "qtd", "funcao": "soma", "label": "Total", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/queries/{query['id']}/subquery-parametros",
        json=[{"coluna_origem": "equipamento", "parametro_destino": "prefixo", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    painel_slug = f"painel_dynamic_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Dynamic"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        ind = res.json()["indicadores"][0]
        assert ind["query_tipo"] == "table_dynamic"
        assert ind["agrupamentos"] == ["fazenda"]
        assert ind["agregacoes"] == [{"coluna": "qtd", "funcao": "soma", "label": "Total"}]
        assert ind["subquery"]["slug"] == sub_slug
        assert ind["subquery"]["tipo"] == "kpi"
        assert ind["subquery"]["parametros"] == [
            {"coluna_origem": "equipamento", "parametro_destino": "prefixo"}
        ]
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        client.delete(f"/api/queries/{sub['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_renderizar_painel_table_dynamic_sem_subquery_retorna_none(client, auth_token):
    query_slug = f"query_dynamic_sem_sub_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Dynamic Sem Subquery",
            "sql_texto": "SELECT 'Fazenda Manga' AS fazenda, 3 AS qtd",
            "tipo": "table_dynamic",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_dynamic_sem_sub_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Dynamic Sem Subquery"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        ind = res.json()["indicadores"][0]
        assert ind["subquery"] is None
        assert ind["agrupamentos"] == []
        assert ind["agregacoes"] == []
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_renderizar_painel_indicador_table_nao_ganha_campos_de_table_dynamic(client, auth_token):
    query_slug = f"query_table_normal_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Table Normal",
            "sql_texto": "SELECT 1 AS valor",
            "tipo": "table",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_table_normal_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Table Normal"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        ind = res.json()["indicadores"][0]
        assert "query_id" not in ind
        assert "subquery_id" not in ind
        assert "agrupamentos" not in ind
        assert "agregacoes" not in ind
        assert "subquery" not in ind
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
