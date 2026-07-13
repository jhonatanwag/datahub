import uuid
import pytest
from datetime import datetime, timezone
from jose import jwt
from config.settings import settings


@pytest.fixture
def sso_ambiente(client, auth_token):
    """Cria empresa (alpha) com SSO habilitado (API key + sso_query_acesso)
    e um painel de teste. Devolve os dados pra cada teste montar seu
    próprio cenário."""
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

    # Query auto-contida (sem precisar de tabela/view real no banco da
    # empresa): libera só esse codigo_usuario pra esse painel_slug.
    sso_query_acesso = (
        f"SELECT painel_slug FROM (VALUES ('{codigo_usuario}', '{painel_slug}')) "
        f"AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1"
    )

    empresa_atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    patch_res = client.patch(
        f"/api/empresas/{alpha['id']}",
        json={
            "slug": empresa_atual["slug"],
            "nome": empresa_atual["nome"],
            "db_host": empresa_atual["db_host"],
            "db_port": empresa_atual["db_port"],
            "db_name": empresa_atual["db_name"],
            "db_user": empresa_atual["db_user"],
            "ativo": empresa_atual["ativo"],
            "sso_query_acesso": sso_query_acesso,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200

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


def test_buscar_painel_por_slug_com_token_externo_de_outro_painel_retorna_403(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        "/api/paineis/slug/painel-que-nao-foi-autorizado",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_buscar_painel_por_slug_com_token_externo_do_proprio_painel_funciona(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/slug/{sso_ambiente['painel_slug']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["id"] == sso_ambiente["painel_id"]


def test_renderizar_painel_injeta_codigo_usuario_do_token_ignorando_query_string(
    client, sso_ambiente, auth_token
):
    query_slug = f"query_sso_teste_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query SSO Teste",
            "sql_texto": "SELECT $1::text AS valor, 'codigo' AS label",
            "tipo": "kpi",
            "empresa_id": sso_ambiente["empresa_id"],
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

    ind_res = client.put(
        f"/api/paineis/{sso_ambiente['painel_id']}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ind_res.status_code == 200

    token = _token_externo(client, sso_ambiente)
    res = client.get(
        f"/api/paineis/{sso_ambiente['painel_id']}/renderizar?codigo_usuario_externo=valor-forjado-pelo-cliente",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    dados = res.json()["indicadores"][0]["dados"]
    assert dados[0]["valor"] == sso_ambiente["codigo_usuario"]

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})


@pytest.fixture
def outro_painel(client, auth_token, sso_ambiente):
    """Um segundo painel, distinto do painel escopado no token externo,
    usado para provar que o token externo NÃO consegue acessá-lo."""
    sufixo = uuid.uuid4().hex[:8]
    slug = f"painel_outro_{sufixo}"
    res = client.post(
        "/api/paineis/",
        json={"slug": slug, "nome": "Outro Painel", "empresa_id": sso_ambiente["empresa_id"]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    painel_id = res.json()["id"]

    try:
        yield painel_id
    finally:
        client.delete(f"/api/paineis/{painel_id}", headers={"Authorization": f"Bearer {auth_token}"})


def test_listar_indicadores_com_token_externo_de_outro_painel_retorna_403(
    client, sso_ambiente, outro_painel
):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/{outro_painel}/indicadores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_listar_indicadores_com_token_externo_do_proprio_painel_funciona(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/{sso_ambiente['painel_id']}/indicadores",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200


def test_listar_variaveis_painel_com_token_externo_de_outro_painel_retorna_403(
    client, sso_ambiente, outro_painel
):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/{outro_painel}/variaveis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_listar_variaveis_painel_com_token_externo_do_proprio_painel_funciona(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/{sso_ambiente['painel_id']}/variaveis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200


def test_sso_trocar_emite_jwt_com_expiracao_curta_de_token_externo(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    now = datetime.now(timezone.utc)

    delta_minutos = (exp - now).total_seconds() / 60

    # Tolerância generosa pra evitar flakiness, mas claramente abaixo dos
    # 480 min do login interno -- prova que usa JWT_EXPIRE_MINUTES_EXTERNO.
    assert delta_minutos < 60
    assert abs(delta_minutos - settings.JWT_EXPIRE_MINUTES_EXTERNO) < 5
