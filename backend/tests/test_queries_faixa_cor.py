import uuid

SQL = "SELECT 'A' AS prop, 'G' AS grupo, 80 AS nota"


def _h(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def _criar(client, auth_token, **overrides):
    return client.post(
        "/api/queries/",
        json={
            "slug": f"teste_faixa_{uuid.uuid4().hex[:6]}",
            "nome": "Teste Faixa",
            "sql_texto": SQL,
            "tipo": "table_dynamic",
            "cache_ttl": 0,
            **overrides,
        },
        headers=_h(auth_token),
    )


def test_criar_query_usa_defaults_de_faixa_cor(client, auth_token):
    res = _criar(client, auth_token)
    assert res.status_code == 200
    body = res.json()
    assert body["faixa_cor_habilitada"] is False
    assert float(body["faixa_cor_ate_vermelho"]) == 70
    assert float(body["faixa_cor_ate_amarelo"]) == 90
    client.delete(f"/api/queries/{body['id']}", headers=_h(auth_token))


def test_criar_e_atualizar_faixa_cor(client, auth_token):
    res = _criar(client, auth_token, faixa_cor_habilitada=True,
                 faixa_cor_ate_vermelho=60, faixa_cor_ate_amarelo=85)
    assert res.status_code == 200
    body = res.json()
    assert body["faixa_cor_habilitada"] is True
    assert float(body["faixa_cor_ate_vermelho"]) == 60
    assert float(body["faixa_cor_ate_amarelo"]) == 85

    patch = client.patch(
        f"/api/queries/{body['id']}",
        json={"faixa_cor_habilitada": False, "faixa_cor_ate_amarelo": 95},
        headers=_h(auth_token),
    )
    assert patch.status_code == 200
    atualizada = patch.json()
    assert atualizada["faixa_cor_habilitada"] is False
    assert float(atualizada["faixa_cor_ate_vermelho"]) == 60
    assert float(atualizada["faixa_cor_ate_amarelo"]) == 95
    client.delete(f"/api/queries/{body['id']}", headers=_h(auth_token))
