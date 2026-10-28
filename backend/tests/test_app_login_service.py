import asyncio
import httpx
import pytest
from fastapi import HTTPException
from services import app_login

EMPRESA = {"slug": "alpha", "url_impressao_base": "https://pso.exemplo/", "app_login_api_key": "k"}


def _com_resposta(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(app_login.httpx, "AsyncClient",
                        lambda **kw: original(transport=transport, **kw))


def _validar(login="maria", senha="x"):
    return asyncio.run(app_login.validar_usuario_app(EMPRESA, login, senha))


def test_valido_devolve_id_e_nome_e_manda_chave_e_corpo(monkeypatch):
    vistos = {}

    def handler(request):
        vistos["url"] = str(request.url)
        vistos["chave"] = request.headers["X-API-Key"]
        vistos["corpo"] = request.content.decode()
        return httpx.Response(200, json={"valido": True, "usuarioId": 7, "nome": "Maria"})

    _com_resposta(monkeypatch, handler)
    assert _validar() == {"usuario_id": 7, "nome": "Maria"}
    assert vistos["url"] == "https://pso.exemplo/servicos/integracao/v1/auth/validar-usuario"
    assert vistos["chave"] == "k"
    assert '"login":"maria"' in vistos["corpo"].replace(" ", "")


def test_invalido_devolve_none(monkeypatch):
    _com_resposta(monkeypatch, lambda r: httpx.Response(200, json={"valido": False}))
    assert _validar() is None


@pytest.mark.parametrize("resposta", [
    httpx.Response(403, json={"mensagem": "Chave de API inválida ou inativa."}),
    httpx.Response(500, text="erro"),
    httpx.Response(200, text="<html>nao e json</html>"),
])
def test_falha_do_servidor_vira_503(monkeypatch, resposta):
    _com_resposta(monkeypatch, lambda r: resposta)
    with pytest.raises(HTTPException) as e:
        _validar()
    assert e.value.status_code == 503


def test_erro_de_rede_vira_503(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("sem rota")
    _com_resposta(monkeypatch, handler)
    with pytest.raises(HTTPException) as e:
        _validar()
    assert e.value.status_code == 503
