import uuid


def test_testar_fonte_nao_persiste_variavel(client, auth_token):
    antes = client.get(
        "/api/variaveis/",
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    res = client.post(
        "/api/variaveis/testar-fonte",
        json={"query_fonte": "SELECT 1 AS valor, 'Um' AS label"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["linhas"] == 1
    assert body["amostra"][0]["valor"] == 1

    depois = client.get(
        "/api/variaveis/",
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()
    assert len(depois) == len(antes)


def test_testar_fonte_com_colunas_erradas_retorna_erro_claro(client, auth_token):
    """Reproduz o bug: query válida e com linhas, mas sem colunas 'valor'/'label'
    — antes ficava com 'ok: true' e a tabela de opções em branco silenciosamente."""
    res = client.post(
        "/api/variaveis/testar-fonte",
        json={"query_fonte": "SELECT 1 AS id, 'Um' AS nome"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "valor" in body["erro"] and "label" in body["erro"]
    assert "linhas" not in body


def test_testar_fonte_com_sql_invalido_retorna_erro_sem_500(client, auth_token):
    res = client.post(
        "/api/variaveis/testar-fonte",
        json={"query_fonte": "SELECT * FROM tabela_que_nao_existe"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["erro"]


def test_testar_fonte_com_empresa_id_valido_usa_banco_da_empresa_escolhida(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    outra_empresa = next(e for e in empresas if e["slug"] != "alpha")

    res = client.post(
        "/api/variaveis/testar-fonte",
        json={"query_fonte": "SELECT 1 AS valor, 'Um' AS label", "empresa_id": outra_empresa["id"]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["linhas"] == 1


def test_testar_fonte_com_empresa_id_invalido_retorna_erro_sem_500(client, auth_token):
    res = client.post(
        "/api/variaveis/testar-fonte",
        json={"query_fonte": "SELECT 1 AS valor, 'Um' AS label", "empresa_id": 999999},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "999999" in body["erro"]


def test_criar_variavel_com_slug_duplicado_retorna_409_nao_500(client, auth_token):
    slug = f"teste_variavel_dropdown_duplicada_{uuid.uuid4().hex[:8]}"
    payload = {
        "slug": slug,
        "nome": "Teste Dropdown Duplicada",
        "tipo": "select",
        "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        "param_names": [slug],
    }
    primeira = client.post(
        "/api/variaveis/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert primeira.status_code == 200
    variavel_id = primeira.json()["id"]

    try:
        segunda = client.post(
            "/api/variaveis/",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert segunda.status_code == 409
    finally:
        client.delete(
            f"/api/variaveis/{variavel_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )


def test_criar_variavel_com_slug_reutilizado_de_desativada_retorna_409_nao_500(client, auth_token):
    """Reproduz o bug: slug de uma variável soft-deletada (ativo=false)
    ainda deve bloquear com 409 (não 500) ao ser reutilizado."""
    slug = f"teste_variavel_dropdown_reuso_slug_{uuid.uuid4().hex[:8]}"
    payload = {
        "slug": slug,
        "nome": "Teste Dropdown Reuso Slug",
        "tipo": "multiselect",
        "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        "param_names": [slug],
    }
    primeira = client.post(
        "/api/variaveis/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert primeira.status_code == 200
    variavel_id = primeira.json()["id"]

    desativar = client.delete(
        f"/api/variaveis/{variavel_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert desativar.status_code == 200

    segunda = client.post(
        "/api/variaveis/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert segunda.status_code == 409
