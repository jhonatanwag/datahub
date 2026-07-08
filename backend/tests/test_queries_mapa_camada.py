MAP_SQL = "SELECT -23.5 AS lat, -46.6 AS lng, 100 AS valor, 'SP' AS label"


def _criar_query_map(client, auth_token, slug, mapa_camada=None):
    body = {
        "slug": slug,
        "nome": "Teste Mapa Camada",
        "sql_texto": MAP_SQL,
        "tipo": "map",
    }
    if mapa_camada is not None:
        body["mapa_camada"] = mapa_camada
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_usa_padrao_por_default(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_default")
    assert res.status_code == 200
    body = res.json()
    assert body["mapa_camada"] == "padrao"
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_com_satelite(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_satelite", mapa_camada="satelite")
    assert res.status_code == 200
    body = res.json()
    assert body["mapa_camada"] == "satelite"
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_com_camada_invalida(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_invalida", mapa_camada="rua")
    assert res.status_code == 400


def test_atualizar_query_mapa_camada(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"mapa_camada": "satelite"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["mapa_camada"] == "satelite"

    invalid_res = client.patch(
        f"/api/queries/{query_id}",
        json={"mapa_camada": "rua"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert invalid_res.status_code == 400

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
