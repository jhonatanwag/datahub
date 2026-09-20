import uuid
from config.settings import settings


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _criar_query_com_n_linhas(client, auth_token, n):
    slug = f"teste_limite_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/api/queries/",
        json={
            "slug": slug, "nome": "Teste Limite Linhas", "tipo": "table", "cache_ttl": 0,
            "sql_texto": f"SELECT g AS valor FROM generate_series(1, {n}) AS g",
        },
        headers=_h(auth_token),
    )
    assert res.status_code == 200
    return slug, res.json()["id"]


def test_query_dentro_do_limite_executa_normalmente(client, auth_token, monkeypatch):
    monkeypatch.setattr(settings, "MAX_LINHAS_QUERY", 10)
    slug, qid = _criar_query_com_n_linhas(client, auth_token, 10)   # exatamente o limite
    try:
        r = client.get(f"/api/queries/executar/{slug}", headers=_h(auth_token))
        assert r.status_code == 200
        assert len(r.json()["data"]) == 10
    finally:
        client.delete(f"/api/queries/{qid}", headers=_h(auth_token))


def test_query_acima_do_limite_e_recusada_com_413_e_mensagem(client, auth_token, monkeypatch):
    monkeypatch.setattr(settings, "MAX_LINHAS_QUERY", 10)
    slug, qid = _criar_query_com_n_linhas(client, auth_token, 11)   # 1 acima
    try:
        r = client.get(f"/api/queries/executar/{slug}", headers=_h(auth_token))
        assert r.status_code == 413
        detalhe = r.json()["detail"]
        assert "10" in detalhe and "filtros" in detalhe.lower()
    finally:
        client.delete(f"/api/queries/{qid}", headers=_h(auth_token))


def test_resultado_recusado_nao_vai_para_o_cache(client, auth_token, monkeypatch):
    """Se estourou o limite, nada pode ter sido gravado no Redis (senão o mesmo estouro
    ocuparia memória do cache mesmo sendo recusado)."""
    import asyncio
    import redis.asyncio as aioredis
    monkeypatch.setattr(settings, "MAX_LINHAS_QUERY", 5)
    slug = f"teste_limite_cache_{uuid.uuid4().hex[:8]}"
    qid = client.post(
        "/api/queries/",
        json={"slug": slug, "nome": "T", "tipo": "table", "cache_ttl": 300,
              "sql_texto": "SELECT g AS valor FROM generate_series(1, 50) AS g"},
        headers=_h(auth_token),
    ).json()["id"]
    try:
        assert client.get(f"/api/queries/executar/{slug}", headers=_h(auth_token)).status_code == 413

        async def _chaves():
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                return await r.keys(f"query:{slug}:*")
            finally:
                await r.aclose()
        assert asyncio.run(_chaves()) == []
    finally:
        client.delete(f"/api/queries/{qid}", headers=_h(auth_token))
