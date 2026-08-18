import uuid
import pytest
from conftest import hard_delete_painel, hard_delete_usuario


@pytest.fixture
def usuario_teste(client, auth_token):
    """Cria um usuário viewer vinculado à empresa alpha, devolve
    id/email/senha pra poder logar como ele nos testes."""
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    sufixo = uuid.uuid4().hex[:8]
    email = f"teste_codigo_{sufixo}@datahub.local"
    senha = "senha12345"

    res = client.post(
        "/api/usuarios/",
        json={"nome": "Usuário Teste Código", "email": email, "senha": senha, "role": "viewer"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    usuario_id = res.json()["id"]

    yield {"id": usuario_id, "email": email, "senha": senha, "empresa_id": alpha["id"]}

    hard_delete_usuario(usuario_id)


def _login_como(client, email, senha, empresa_id):
    login_res = client.post("/api/auth/login", json={"email": email, "senha": senha})
    assert login_res.status_code == 200
    sel_res = client.post(
        "/api/auth/selecionar-empresa",
        json={"session_token": login_res.json()["session_token"], "empresa_id": empresa_id},
    )
    assert sel_res.status_code == 200
    return sel_res.json()["token"]


def test_vincular_empresas_salva_e_devolve_codigo_usuario_externo(client, auth_token, usuario_teste):
    res = client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"], "codigo_usuario_externo": "COD123"}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200

    listar_res = client.get(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert listar_res.status_code == 200
    vinculo = next(e for e in listar_res.json() if e["id"] == usuario_teste["empresa_id"])
    assert vinculo["codigo_usuario_externo"] == "COD123"


def test_vincular_empresas_sem_codigo_fica_null(client, auth_token, usuario_teste):
    res = client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"]}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200

    listar_res = client.get(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    vinculo = next(e for e in listar_res.json() if e["id"] == usuario_teste["empresa_id"])
    assert vinculo["codigo_usuario_externo"] is None


def test_vincular_empresas_atualiza_codigo_existente(client, auth_token, usuario_teste):
    client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"], "codigo_usuario_externo": "PRIMEIRO"}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"], "codigo_usuario_externo": "SEGUNDO"}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    listar_res = client.get(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    vinculo = next(e for e in listar_res.json() if e["id"] == usuario_teste["empresa_id"])
    assert vinculo["codigo_usuario_externo"] == "SEGUNDO"


def test_renderizar_painel_injeta_codigo_usuario_externo_do_vinculo_ignorando_query_string(
    client, auth_token, usuario_teste
):
    """Usuário interno logado normalmente (não SSO) com código vinculado à
    empresa ativa: o filtro codigo_usuario_externo tem que vir travado no
    valor vinculado, mesmo se a URL tentar passar outro."""
    client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"], "codigo_usuario_externo": "MEU_CODIGO"}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    query_slug = f"query_codigo_teste_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Código Teste",
            "sql_texto": "SELECT $1::text AS valor, 'codigo' AS label",
            "tipo": "kpi",
            "empresa_id": usuario_teste["empresa_id"],
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    param_res = client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "codigo_usuario_externo", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert param_res.status_code == 200

    painel_slug = f"painel_codigo_teste_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Código Teste", "empresa_id": usuario_teste["empresa_id"]},
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
        token_usuario = _login_como(
            client, usuario_teste["email"], usuario_teste["senha"], usuario_teste["empresa_id"]
        )

        res = client.get(
            f"/api/paineis/{painel_id}/renderizar?codigo_usuario_externo=valor-forjado-pelo-cliente",
            headers={"Authorization": f"Bearer {token_usuario}"},
        )
        assert res.status_code == 200
        dados = res.json()["indicadores"][0]["dados"]
        assert dados[0]["valor"] == "MEU_CODIGO"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})


def test_executar_query_injeta_codigo_usuario_externo_do_vinculo_ignorando_query_string(
    client, auth_token, usuario_teste
):
    """GET /api/queries/executar/{slug}: o filtro codigo_usuario_externo tem
    que vir travado no valor vinculado, mesmo se a URL tentar passar outro
    (evita que um usuário externo leia dados de outro forjando o parâmetro)."""
    client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"], "codigo_usuario_externo": "MEU_CODIGO"}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    query_slug = f"query_codigo_executar_teste_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Código Executar Teste",
            "sql_texto": "SELECT $1::text AS valor, 'codigo' AS label",
            "tipo": "kpi",
            "empresa_id": usuario_teste["empresa_id"],
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    param_res = client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "codigo_usuario_externo", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert param_res.status_code == 200

    try:
        token_usuario = _login_como(
            client, usuario_teste["email"], usuario_teste["senha"], usuario_teste["empresa_id"]
        )

        res = client.get(
            f"/api/queries/executar/{query_slug}?codigo_usuario_externo=valor-forjado-pelo-cliente",
            headers={"Authorization": f"Bearer {token_usuario}"},
        )
        assert res.status_code == 200
        assert res.json()["data"][0]["valor"] == "MEU_CODIGO"
    finally:
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})


def test_renderizar_painel_sem_codigo_vinculado_nao_injeta_filtro(client, auth_token, usuario_teste):
    """Usuário sem código vinculado (padrão) não deve ter o filtro
    codigo_usuario_externo forçado -- a query cai no valor_padrao normal."""
    client.post(
        f"/api/usuarios/{usuario_teste['id']}/empresas",
        json={"vinculos": [{"empresa_id": usuario_teste["empresa_id"]}]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    query_slug = f"query_sem_codigo_teste_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Sem Código Teste",
            "sql_texto": "SELECT COALESCE($1::text, 'sem-filtro') AS valor, 'codigo' AS label",
            "tipo": "kpi",
            "empresa_id": usuario_teste["empresa_id"],
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    param_res = client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "codigo_usuario_externo", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert param_res.status_code == 200

    painel_slug = f"painel_sem_codigo_teste_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Sem Código Teste", "empresa_id": usuario_teste["empresa_id"]},
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
        token_usuario = _login_como(
            client, usuario_teste["email"], usuario_teste["senha"], usuario_teste["empresa_id"]
        )

        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {token_usuario}"},
        )
        assert res.status_code == 200
        dados = res.json()["indicadores"][0]["dados"]
        assert dados[0]["valor"] == "sem-filtro"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
