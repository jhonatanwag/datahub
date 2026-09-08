import asyncio
import pytest
from conftest import _connect_meta, hard_delete_empresa


@pytest.fixture
def empresa_temp():
    """Insere uma empresa direto no banco — o POST da API tenta conectar no
    banco de dados da empresa, o que não dá pra garantir em teste — e limpa no fim."""
    async def _criar():
        conn = await _connect_meta()
        try:
            row = await conn.fetchrow("""
                INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo)
                VALUES ('teste-endereco-rel', 'Teste Endereco Rel', 'x', 5432, 'x', 'x', 'x', true)
                RETURNING id
            """)
            return row["id"]
        finally:
            await conn.close()
    empresa_id = asyncio.run(_criar())
    yield empresa_id
    hard_delete_empresa(empresa_id)


PAYLOAD_BASE = {
    "slug": "teste-endereco-rel", "nome": "Teste Endereco Rel",
    "db_host": "x", "db_port": 5432, "db_name": "x", "db_user": "x", "ativo": True,
}


def test_patch_e_get_devolvem_endereco_cnpj(client, auth_token, empresa_temp):
    h = {"Authorization": f"Bearer {auth_token}"}
    r = client.patch(f"/api/empresas/{empresa_temp}", headers=h, json={
        **PAYLOAD_BASE,
        "endereco": "Rua Teste, 123 - Centro - CEP 00000-000",
        "cnpj": "12.345.678/0001-90",
    })
    assert r.status_code == 200

    body = client.get(f"/api/empresas/{empresa_temp}", headers=h).json()
    assert body["endereco"] == "Rua Teste, 123 - Centro - CEP 00000-000"
    assert body["cnpj"] == "12.345.678/0001-90"


def test_listar_empresas_inclui_campos(client, auth_token, empresa_temp):
    h = {"Authorization": f"Bearer {auth_token}"}
    client.patch(f"/api/empresas/{empresa_temp}", headers=h,
                 json={**PAYLOAD_BASE, "endereco": "Av X", "cnpj": "00"})
    lista = client.get("/api/empresas/", headers=h).json()
    alvo = next(e for e in lista if e["id"] == empresa_temp)
    assert alvo["endereco"] == "Av X"
    assert alvo["cnpj"] == "00"


def test_me_inclui_company_endereco_cnpj(client, auth_token):
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"}).json()
    assert "company_endereco" in me
    assert "company_cnpj" in me
