import uuid
from conftest import hard_delete_painel


AUTH = lambda t: {"Authorization": f"Bearer {t}"}


def test_criar_painel_com_orientacao_paisagem(client, auth_token):
    slug = f"painel_orient_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/api/paineis/",
        json={"slug": slug, "nome": "Painel Orientação", "impressao_orientacao": "paisagem"},
        headers=AUTH(auth_token),
    )
    assert res.status_code == 200
    painel_id = res.json()["id"]
    try:
        assert res.json()["impressao_orientacao"] == "paisagem"

        detalhe = client.get(f"/api/paineis/{painel_id}", headers=AUTH(auth_token)).json()
        assert detalhe["impressao_orientacao"] == "paisagem"
    finally:
        hard_delete_painel(painel_id)


def test_criar_painel_orientacao_default_retrato(client, auth_token):
    slug = f"painel_orient_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/api/paineis/",
        json={"slug": slug, "nome": "Painel Sem Orientação"},
        headers=AUTH(auth_token),
    )
    assert res.status_code == 200
    painel_id = res.json()["id"]
    try:
        assert res.json()["impressao_orientacao"] == "retrato"
    finally:
        hard_delete_painel(painel_id)


def test_patch_painel_altera_orientacao(client, auth_token):
    slug = f"painel_orient_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": slug, "nome": "Painel Patch Orientação"},
        headers=AUTH(auth_token),
    ).json()["id"]
    try:
        res = client.patch(
            f"/api/paineis/{painel_id}",
            json={"impressao_orientacao": "paisagem"},
            headers=AUTH(auth_token),
        )
        assert res.status_code == 200
        assert res.json()["impressao_orientacao"] == "paisagem"
    finally:
        hard_delete_painel(painel_id)
