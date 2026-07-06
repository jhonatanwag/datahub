import pytest
from fastapi.testclient import TestClient
from main import app

ADMIN_EMAIL = "admin@datahub.local"
ADMIN_SENHA = "admin123"
EMPRESA_SLUG = "alpha"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_token(client):
    login_res = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "senha": ADMIN_SENHA},
    )
    assert login_res.status_code == 200
    body = login_res.json()
    empresa = next(e for e in body["empresas"] if e["slug"] == EMPRESA_SLUG)

    sel_res = client.post(
        "/api/auth/selecionar-empresa",
        json={"session_token": body["session_token"], "empresa_id": empresa["id"]},
    )
    assert sel_res.status_code == 200
    token = sel_res.json()["token"]

    yield token

    # Restaura o padrão para não deixar o usuário admin (compartilhado entre
    # execuções de teste) marcado como 'claro' depois da suíte rodar.
    client.put(
        "/api/auth/tema",
        json={"tema": "escuro"},
        headers={"Authorization": f"Bearer {token}"},
    )
