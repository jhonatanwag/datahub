import asyncio
import asyncpg
import pytest
from fastapi.testclient import TestClient
from main import app
from config.settings import settings

ADMIN_EMAIL = "admin@datahub.local"
ADMIN_SENHA = "admin123"
EMPRESA_SLUG = "alpha"


async def _connect_meta():
    return await asyncpg.connect(
        host=settings.META_DB_HOST, port=settings.META_DB_PORT,
        database=settings.META_DB_NAME, user=settings.META_DB_USER,
        password=settings.META_DB_PASS,
    )


def hard_delete_painel(painel_id: int):
    """Remove de verdade um painel criado pra teste (cascade cuida de
    indicadores/variaveis/painel_usuarios) -- o DELETE da API só desativa
    (ativo=false), o que deixaria lixo permanente no banco de dev
    compartilhado a cada execução da suíte."""
    async def _exec():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM paineis WHERE id = $1", painel_id)
        finally:
            await conn.close()
    asyncio.run(_exec())


def hard_delete_usuario(usuario_id: int):
    """Mesma lógica de hard_delete_painel, pra usuários criados em teste."""
    async def _exec():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM usuario_empresas WHERE usuario_id = $1", usuario_id)
            await conn.execute("DELETE FROM usuarios WHERE id = $1", usuario_id)
        finally:
            await conn.close()
    asyncio.run(_exec())


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
