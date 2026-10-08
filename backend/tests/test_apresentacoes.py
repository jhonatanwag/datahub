import uuid
import pytest
from conftest import hard_delete_apresentacao, hard_delete_painel


def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def painel_id(client, auth_token):
    res = client.post(
        "/api/paineis/",
        json={"slug": f"painel_apr_{uuid.uuid4().hex[:8]}", "nome": "Painel p/ Apresentação"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    pid = res.json()["id"]
    yield pid
    hard_delete_painel(pid)


@pytest.fixture
def apresentacao(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": f"apr_{uuid.uuid4().hex[:8]}", "nome": "TV Teste"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    apr = res.json()
    yield apr
    hard_delete_apresentacao(apr["id"])


def test_criar_apresentacao_usa_padroes(apresentacao):
    assert apresentacao["intervalo_atualizacao_seg"] == 300
    assert apresentacao["ativo"] is True
    assert apresentacao["empresa_id"] is None


def test_slug_invalido_retorna_422(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": "Com-Hifen", "nome": "x"},
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_slug_duplicado_retorna_409(client, auth_token, apresentacao):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": apresentacao["slug"], "nome": "outra"},
        headers=H(auth_token),
    )
    assert res.status_code == 409


def test_intervalo_menor_que_30_retorna_422(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": f"apr_{uuid.uuid4().hex[:8]}", "nome": "x", "intervalo_atualizacao_seg": 10},
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_patch_atualiza_campos(client, auth_token, apresentacao):
    res = client.patch(
        f"/api/apresentacoes/{apresentacao['id']}",
        json={"nome": "Novo nome", "intervalo_atualizacao_seg": 60},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    assert res.json()["nome"] == "Novo nome"
    assert res.json()["intervalo_atualizacao_seg"] == 60


def test_delete_desativa(client, auth_token, apresentacao):
    res = client.delete(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token))
    assert res.status_code == 200
    got = client.get(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token)).json()
    assert got["ativo"] is False


def test_salvar_slides_grava_ordem_e_filtros(client, auth_token, apresentacao, painel_id):
    corpo = [
        {"painel_id": painel_id, "duracao_seg": 20, "filtros": {"data_inicio": "mes_atual_inicio"}},
        {"painel_id": painel_id, "duracao_seg": 45, "filtros": {}},
    ]
    res = client.put(f"/api/apresentacoes/{apresentacao['id']}/slides", json=corpo, headers=H(auth_token))
    assert res.status_code == 200
    slides = client.get(f"/api/apresentacoes/{apresentacao['id']}/slides", headers=H(auth_token)).json()
    assert [s["ordem"] for s in slides] == [0, 1]
    assert [s["duracao_seg"] for s in slides] == [20, 45]
    assert slides[0]["filtros"] == {"data_inicio": "mes_atual_inicio"}
    assert slides[0]["painel_ativo"] is True


def test_salvar_slides_com_painel_inexistente_retorna_422_e_mantem_lista(client, auth_token, apresentacao, painel_id):
    url = f"/api/apresentacoes/{apresentacao['id']}/slides"
    client.put(url, json=[{"painel_id": painel_id}], headers=H(auth_token))
    res = client.put(url, json=[{"painel_id": 99999999}], headers=H(auth_token))
    assert res.status_code == 422
    assert len(client.get(url, headers=H(auth_token)).json()) == 1


def test_duracao_menor_que_5_retorna_422(client, auth_token, apresentacao, painel_id):
    res = client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id, "duracao_seg": 1}],
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_salvar_e_listar_usuarios(client, auth_token, apresentacao):
    me = client.get("/api/auth/me", headers=H(auth_token)).json()
    res = client.put(f"/api/apresentacoes/{apresentacao['id']}/usuarios", json=[me["id"]], headers=H(auth_token))
    assert res.status_code == 200
    lista = client.get(f"/api/apresentacoes/{apresentacao['id']}/usuarios", headers=H(auth_token)).json()
    assert [u["id"] for u in lista] == [me["id"]]


# ── Task 3: /minhas e /executar ──────────────────────────────

from conftest import hard_delete_usuario


@pytest.fixture
def usuario_comum(client, auth_token):
    alpha = next(
        e for e in client.get("/api/empresas/", headers=H(auth_token)).json() if e["slug"] == "alpha"
    )
    email = f"apr_{uuid.uuid4().hex[:8]}@datahub.local"
    senha = "senha12345"
    res = client.post(
        "/api/usuarios/",
        json={"nome": "Viewer Apr", "email": email, "senha": senha, "role": "viewer"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    uid = res.json()["id"]
    vinc = client.post(
        f"/api/usuarios/{uid}/empresas",
        json={"vinculos": [{"empresa_id": alpha["id"]}]},
        headers=H(auth_token),
    )
    assert vinc.status_code == 200
    login = client.post("/api/auth/login", json={"email": email, "senha": senha}).json()
    sel = client.post(
        "/api/auth/selecionar-empresa",
        json={"session_token": login["session_token"], "empresa_id": alpha["id"]},
    ).json()
    yield {"id": uid, "token": sel["token"]}
    hard_delete_usuario(uid)


def test_executar_sem_slides_devolve_lista_vazia(client, auth_token, apresentacao):
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    assert res.status_code == 200
    assert res.json()["slides"] == []


def test_executar_devolve_slides_em_ordem_com_painel(client, auth_token, apresentacao, painel_id):
    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id, "duracao_seg": 12, "filtros": {"hoje": "hoje"}}],
        headers=H(auth_token),
    )
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    body = res.json()
    assert body["intervalo_atualizacao_seg"] == 300
    assert body["slides"][0]["duracao_seg"] == 12
    assert body["slides"][0]["filtros"] == {"hoje": "hoje"}
    assert body["slides"][0]["painel"]["id"] == painel_id


def test_executar_pula_painel_inativo(client, auth_token, apresentacao, painel_id):
    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id}],
        headers=H(auth_token),
    )
    client.delete(f"/api/paineis/{painel_id}", headers=H(auth_token))  # desativa
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    assert res.status_code == 200
    assert res.json()["slides"] == []


def test_minhas_admin_ve_todas_as_ativas(client, auth_token, apresentacao):
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=H(auth_token)).json()]
    assert apresentacao["id"] in ids


def test_minhas_ignora_inativas(client, auth_token, apresentacao):
    client.delete(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token))
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=H(auth_token)).json()]
    assert apresentacao["id"] not in ids


def test_usuario_comum_so_ve_e_executa_as_vinculadas(client, auth_token, apresentacao, usuario_comum):
    h = H(usuario_comum["token"])
    antes = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=h).json()]
    assert apresentacao["id"] not in antes
    assert client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=h).status_code == 404

    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/usuarios",
        json=[usuario_comum["id"]],
        headers=H(auth_token),
    )
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=h).json()]
    assert apresentacao["id"] in ids
    assert client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=h).status_code == 200


def test_usuario_comum_nao_administra(client, usuario_comum):
    res = client.post(
        "/api/apresentacoes/", json={"slug": "x_y", "nome": "x"}, headers=H(usuario_comum["token"])
    )
    assert res.status_code == 403
