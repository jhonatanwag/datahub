def test_atualizar_tema_valor_valido(client, auth_token):
    res = client.put(
        "/api/auth/tema",
        json={"tema": "claro"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json() == {"tema": "claro"}

    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["tema"] == "claro"


def test_atualizar_tema_valor_invalido(client, auth_token):
    res = client.put(
        "/api/auth/tema",
        json={"tema": "azul"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 422


def test_atualizar_tema_sem_autenticacao(client):
    res = client.put("/api/auth/tema", json={"tema": "claro"})
    assert res.status_code == 403
