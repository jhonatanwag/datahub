import uuid


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _criar_query(client, token, **over):
    slug = over.pop("slug", f"qb_{uuid.uuid4().hex[:8]}")
    body = {
        "slug": slug, "nome": over.pop("nome", "Q"),
        "sql_texto": over.pop("sql_texto", "SELECT 1 AS valor"),
        "tipo": over.pop("tipo", "table"), "cache_ttl": 0,
    }
    body.update(over)
    r = client.post("/api/queries/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_derivada_executa_via_cte_da_base(client, auth_token):
    t = auth_token
    base = _criar_query(
        client, t,
        sql_texto="SELECT 1 AS grupo, 10 AS valor UNION ALL SELECT 2, 20 UNION ALL SELECT 1, 5",
    )
    derivada = _criar_query(
        client, t, tipo="chart_bar",
        sql_texto="SELECT grupo AS label, sum(valor) AS valor FROM base GROUP BY grupo ORDER BY 1",
        query_base_id=base["id"],
    )
    try:
        res = client.get(f"/api/queries/executar/{derivada['slug']}", headers=_headers(t))
        assert res.status_code == 200, res.text
        dados = res.json()["data"]
        assert dados == [{"label": 1, "valor": 15}, {"label": 2, "valor": 20}]
    finally:
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))
