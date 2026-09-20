import asyncio
import pytest
from conftest import _connect_meta, hard_delete_painel, ADMIN_EMAIL


def _redis():
    import redis.asyncio as aioredis
    from config.settings import settings
    return aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


def test_trocar_pdf_token_uso_unico(client):
    async def _set():
        r = _redis()
        await r.setex("pdf_exchange:tok-teste-123", 60, "jwt-fake-abc")
        await r.aclose()
    asyncio.run(_set())

    r1 = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "tok-teste-123"})
    assert r1.status_code == 200
    assert r1.json()["token"] == "jwt-fake-abc"

    r2 = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "tok-teste-123"})
    assert r2.status_code == 401


def test_trocar_pdf_token_inexistente(client):
    r = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "nao-existe"})
    assert r.status_code == 401


@pytest.fixture
def painel_temp():
    async def _criar():
        conn = await _connect_meta()
        try:
            uid = await conn.fetchval("SELECT id FROM usuarios WHERE email = $1", ADMIN_EMAIL)
            row = await conn.fetchrow(
                "INSERT INTO paineis (slug, nome) VALUES ('painel_pdf_teste', 'Painel PDF Teste') RETURNING id"
            )
            await conn.execute(
                "INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES ($1, $2)",
                row["id"], uid,
            )
            return row["id"]
        finally:
            await conn.close()
    pid = asyncio.run(_criar())
    yield pid
    hard_delete_painel(pid)


def test_relatorio_pdf_sem_auth_401(client, painel_temp):
    r = client.get("/api/paineis/slug/painel_pdf_teste/relatorio-pdf")
    assert r.status_code in (401, 403)


def test_relatorio_pdf_chama_renderer_e_devolve_pdf(client, auth_token, painel_temp, monkeypatch):
    import httpx

    class FakeResp:
        status_code = 200
        content = b"%PDF-1.4 fake"
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            assert kw["headers"]["X-Renderer-Secret"]  # segredo enviado
            assert "pdf_token=" in kw["json"]["url"]     # token na URL do renderer
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = client.get(
        "/api/paineis/slug/painel_pdf_teste/relatorio-pdf?data_inicio=2026-01-01",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == b"%PDF-1.4 fake"


def test_relatorio_pdf_502_quando_renderer_cai(client, auth_token, painel_temp, monkeypatch):
    import httpx

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            raise httpx.ConnectError("recusado")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = client.get(
        "/api/paineis/slug/painel_pdf_teste/relatorio-pdf",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 502


def test_relatorio_pdf_sem_acesso_404(client, auth_token, monkeypatch):
    async def _criar():
        conn = await _connect_meta()
        try:
            row = await conn.fetchrow(
                "INSERT INTO paineis (slug, nome) VALUES ('painel_pdf_sem_acesso', 'Sem Acesso') RETURNING id"
            )
            return row["id"]
        finally:
            await conn.close()
    pid = asyncio.run(_criar())
    try:
        r = client.get(
            "/api/paineis/slug/painel_pdf_sem_acesso/relatorio-pdf",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert r.status_code == 404
    finally:
        hard_delete_painel(pid)


def _renderer_responde(monkeypatch, status=None, corpo=None, excecao=None):
    """Troca o httpx.AsyncClient por um que devolve `status/corpo` (ou levanta `excecao`)."""
    import httpx

    class FakeResp:
        def __init__(self):
            self.status_code = status
            self.content = b""
            self._corpo = corpo or {}
        def json(self): return self._corpo
        def raise_for_status(self):
            raise httpx.HTTPStatusError("erro", request=None, response=self)

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            if excecao:
                raise excecao
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


def _pedir_pdf(client, auth_token):
    return client.get(
        "/api/paineis/slug/painel_pdf_teste/relatorio-pdf",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_relatorio_pdf_relatorio_grande_demais_repassa_413_com_a_mensagem(client, auth_token, painel_temp, monkeypatch):
    _renderer_responde(monkeypatch, 413, {"erro": "Relatório grande demais. Reduza o período."})
    r = _pedir_pdf(client, auth_token)
    assert r.status_code == 413
    assert "Reduza o período" in r.json()["detail"]


def test_relatorio_pdf_renderer_ocupado_repassa_503(client, auth_token, painel_temp, monkeypatch):
    _renderer_responde(monkeypatch, 503, {"erro": "Gerador de PDF ocupado."})
    r = _pedir_pdf(client, auth_token)
    assert r.status_code == 503
    assert "ocupado" in r.json()["detail"]


def test_relatorio_pdf_tempo_esgotado_no_renderer_repassa_504(client, auth_token, painel_temp, monkeypatch):
    _renderer_responde(monkeypatch, 504, {"erro": "Tempo esgotado ao gerar o PDF."})
    r = _pedir_pdf(client, auth_token)
    assert r.status_code == 504


def test_relatorio_pdf_timeout_do_backend_vira_504(client, auth_token, painel_temp, monkeypatch):
    import httpx
    _renderer_responde(monkeypatch, excecao=httpx.ReadTimeout("demorou"))
    r = _pedir_pdf(client, auth_token)
    assert r.status_code == 504


def test_relatorio_pdf_falha_generica_do_renderer_continua_502(client, auth_token, painel_temp, monkeypatch):
    _renderer_responde(monkeypatch, 500, {"erro": "Falha ao gerar o PDF."})
    r = _pedir_pdf(client, auth_token)
    assert r.status_code == 502
