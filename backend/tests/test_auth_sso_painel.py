import asyncio
import uuid
import asyncpg
import pytest

VIEW_NAME = "vw_datahub_sso_acesso"


def _run(coro):
    return asyncio.run(coro)


async def _conn_alpha_admin():
    return await asyncpg.connect(
        host="postgres", port=5432, database="alpha_db",
        user="postgres", password="postgres123",
    )


def _criar_view_acesso(codigo_usuario, painel_slug):
    async def _go():
        conn = await _conn_alpha_admin()
        try:
            await conn.execute(f"""
                CREATE OR REPLACE VIEW {VIEW_NAME} AS
                SELECT '{codigo_usuario}'::text AS codigo_usuario,
                       '{painel_slug}'::text AS painel_slug
            """)
            await conn.execute(f"GRANT SELECT ON {VIEW_NAME} TO alpha_user")
        finally:
            await conn.close()
    _run(_go())


def _dropar_view_acesso():
    async def _go():
        conn = await _conn_alpha_admin()
        try:
            await conn.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
        finally:
            await conn.close()
    _run(_go())


@pytest.fixture
def sso_ambiente(client, auth_token):
    """Cria empresa (alpha) com SSO habilitado + view de acesso liberando
    um codigo_usuario/painel_slug específicos. Devolve os dados pra cada teste
    montar seu próprio cenário, e limpa a view no final."""
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    api_key_res = client.post(
        f"/api/empresas/{alpha['id']}/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert api_key_res.status_code == 200
    api_key = api_key_res.json()["api_key"]

    sufixo = uuid.uuid4().hex[:8]
    codigo_usuario = f"user_{sufixo}"
    painel_slug = f"painel_sso_teste_{sufixo}"

    _criar_view_acesso(codigo_usuario, painel_slug)

    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel SSO Teste", "empresa_id": alpha["id"]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert painel_res.status_code == 200
    painel_id = painel_res.json()["id"]

    yield {
        "empresa_slug": "alpha",
        "empresa_id": alpha["id"],
        "api_key": api_key,
        "codigo_usuario": codigo_usuario,
        "painel_slug": painel_slug,
        "painel_id": painel_id,
    }

    _dropar_view_acesso()
    client.delete(f"/api/paineis/{painel_id}", headers={"Authorization": f"Bearer {auth_token}"})


def test_sso_painel_sucesso_devolve_redirect_url_com_exchange(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 200
    redirect_url = res.json()["redirect_url"]
    assert "/sso?exchange=" in redirect_url


def test_sso_painel_api_key_errada_retorna_401(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": "chave-errada-completamente",
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 401


def test_sso_painel_empresa_inexistente_retorna_401(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": "empresa-que-nao-existe",
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 401


def test_sso_painel_slug_de_outra_empresa_retorna_404(client, sso_ambiente, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    # A intenção do teste é usar um slug de painel que não pertence à "alpha"
    # (nomeado com base em outra empresa qualquer só pra ser único); o nome
    # da outra empresa em si não importa, então pegamos qualquer uma != alpha
    # em vez de depender de uma empresa "beta" fixa que pode não existir no
    # seed deste ambiente.
    outra_empresa = next(e for e in empresas if e["slug"] != "alpha")

    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": f"painel-que-so-existe-em-outra-empresa-{outra_empresa['id']}",
        },
    )
    assert res.status_code == 404


def test_sso_painel_sem_acesso_na_view_retorna_403(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": "codigo-sem-permissao-nenhuma",
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 403


def test_sso_trocar_token_valido_emite_jwt_externo(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]

    res = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert res.status_code == 200
    body = res.json()
    assert body["painel_slug"] == sso_ambiente["painel_slug"]
    assert len(body["token"]) > 20


def test_sso_trocar_token_ja_usado_retorna_401(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]

    primeira = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert primeira.status_code == 200

    segunda = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert segunda.status_code == 401


def test_sso_trocar_token_invalido_retorna_401(client):
    res = client.post("/api/auth/sso/trocar", json={"exchange": "token-que-nunca-existiu"})
    assert res.status_code == 401


def _token_externo(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]
    return client.post("/api/auth/sso/trocar", json={"exchange": exchange}).json()["token"]


def test_me_com_token_externo_devolve_empresa_real_e_codigo_usuario(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "externo"
    assert body["id"] is None
    assert body["company_slug"] == "alpha"
    assert body["company_name"] == "Empresa Alpha Ltda"
    assert body["codigo_usuario"] == sso_ambiente["codigo_usuario"]
    assert body["painel_slug"] == sso_ambiente["painel_slug"]
