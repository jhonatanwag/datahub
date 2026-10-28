import uuid
import pytest
from jose import jwt
from fastapi import HTTPException
from config.settings import settings
import redis as redis_sync
from routes import auth as auth_routes


def _patch_empresa(client, auth_token, empresa_id, **extras):
    h = {"Authorization": f"Bearer {auth_token}"}
    atual = client.get(f"/api/empresas/{empresa_id}", headers=h).json()
    body = {
        "slug": atual["slug"], "nome": atual["nome"], "db_host": atual["db_host"],
        "db_port": atual["db_port"], "db_name": atual["db_name"], "db_user": atual["db_user"],
        "ativo": atual["ativo"], "sso_query_acesso": atual["sso_query_acesso"],
        "url_impressao_base": atual["url_impressao_base"],
        **extras,
    }
    res = client.patch(f"/api/empresas/{empresa_id}", json=body, headers=h)
    assert res.status_code == 200, res.text
    return atual


@pytest.fixture
def app_login_ambiente(client, auth_token, monkeypatch):
    """Empresa alpha com login-app configurado e sso_query_acesso que libera um painel pro usuário 42.
    O PsoEducare é simulado (monkeypatch em validar_usuario_app). Restaura a empresa no fim."""
    h = {"Authorization": f"Bearer {auth_token}"}
    alpha = next(e for e in client.get("/api/empresas/", headers=h).json() if e["slug"] == "alpha")
    painel = f"painel_loginapp_{uuid.uuid4().hex[:8]}"
    query = (f"SELECT painel_slug FROM (VALUES ('42', '{painel}')) "
             f"AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1")
    original = _patch_empresa(client, auth_token, alpha["id"], sso_query_acesso=query,
                              url_impressao_base="https://psoeducare.exemplo/Alpha/", app_login_api_key="chave-x")

    chamadas = []

    async def falso_validar(empresa, login, senha):
        chamadas.append((empresa["slug"], login, senha, empresa["app_login_api_key"]))
        if login == "maria" and senha == "certa":
            return {"usuario_id": 42, "nome": "Maria"}
        if login == "semacesso" and senha == "certa":
            return {"usuario_id": 99, "nome": "Sem Acesso"}
        return None

    monkeypatch.setattr(auth_routes, "validar_usuario_app", falso_validar)

    def limpar_falhas():
        # cliente síncrono: o redis async global é preso ao loop do TestClient
        r = redis_sync.Redis.from_url(settings.REDIS_URL)
        for chave in r.keys("loginapp:falhas:alpha:*"):
            r.delete(chave)
        r.close()
    limpar_falhas()

    yield {"painel": painel, "chamadas": chamadas, "empresa_id": alpha["id"]}

    limpar_falhas()
    _patch_empresa(client, auth_token, alpha["id"], sso_query_acesso=original["sso_query_acesso"],
                   url_impressao_base=original["url_impressao_base"], app_login_api_key="")


def _login(client, login, senha, empresa="alpha"):
    return client.post("/api/auth/login-app",
                       json={"empresa_slug": empresa, "login": login, "senha": senha})


def test_login_app_sucesso_devolve_token_externo_com_paineis(client, app_login_ambiente):
    res = _login(client, "maria", "certa")
    assert res.status_code == 200
    payload = jwt.decode(res.json()["token"], settings.JWT_SECRET, algorithms=["HS256"])
    assert payload["tipo"] == "externo"
    assert payload["codigo_usuario"] == "42"
    assert payload["paineis_liberados"] == [app_login_ambiente["painel"]]
    assert app_login_ambiente["chamadas"][0][3] == "chave-x"


def test_login_app_token_funciona_em_me(client, app_login_ambiente):
    token = _login(client, "maria", "certa").json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "externo"


def test_login_app_senha_errada_retorna_401(client, app_login_ambiente):
    assert _login(client, "maria", "errada").status_code == 401


def test_login_app_empresa_inexistente_retorna_401_igual(client, app_login_ambiente):
    res = _login(client, "maria", "certa", empresa="nao-existe")
    assert res.status_code == 401
    assert res.json()["detail"] == "Credenciais inválidas"
    assert app_login_ambiente["chamadas"] == []


def test_login_app_usuario_sem_paineis_retorna_403(client, app_login_ambiente):
    assert _login(client, "semacesso", "certa").status_code == 403


def test_login_app_bloqueia_apos_varias_falhas_mesmo_com_senha_certa(client, app_login_ambiente):
    for _ in range(auth_routes.LOGIN_APP_MAX_FALHAS):
        assert _login(client, "maria", "errada").status_code == 401
    assert _login(client, "maria", "certa").status_code == 429


def test_login_app_empresa_sem_configuracao_retorna_401(client, auth_token, app_login_ambiente):
    _patch_empresa(client, auth_token, app_login_ambiente["empresa_id"], url_impressao_base="")
    assert _login(client, "maria", "certa").status_code == 401
    assert app_login_ambiente["chamadas"] == []


def test_login_app_psoeducare_fora_do_ar_retorna_503(client, app_login_ambiente, monkeypatch):
    async def fora(empresa, login, senha):
        raise HTTPException(status_code=503, detail="Não foi possível validar o login agora")
    monkeypatch.setattr(auth_routes, "validar_usuario_app", fora)
    assert _login(client, "maria", "certa").status_code == 503


def test_empresa_nao_expoe_api_key_do_app(client, auth_token, app_login_ambiente):
    h = {"Authorization": f"Bearer {auth_token}"}
    emp = client.get(f"/api/empresas/{app_login_ambiente['empresa_id']}", headers=h).json()
    assert emp["app_login_api_key_configurada"] is True
    assert "app_login_api_key" not in emp
