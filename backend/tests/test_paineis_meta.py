import uuid
from conftest import hard_delete_painel


def test_renderizar_painel_inclui_campos_de_meta_do_indicador(client, auth_token):
    query_slug = f"query_meta_painel_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Meta Painel",
            "sql_texto": "SELECT 50 AS valor, 10 AS meta_inicio, 100 AS meta_fim",
            "tipo": "table",
            "cache_ttl": 0,
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
            "meta_cor_dentro": "#00ff00",
            "meta_cor_fora": "#ff0000",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    painel_slug = f"painel_meta_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Meta"},
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
        assert indicador["meta_habilitada"] is True
        assert indicador["meta_coluna_valor"] == "valor"
        assert indicador["meta_coluna_inicio"] == "meta_inicio"
        assert indicador["meta_coluna_fim"] == "meta_fim"
        assert indicador["meta_cor_dentro"] == "#00ff00"
        assert indicador["meta_cor_fora"] == "#ff0000"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
