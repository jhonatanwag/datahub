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


def test_criar_derivada_com_base_e_persistida(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, sql_texto="SELECT 1 AS grupo, 10 AS valor")
    derivada = _criar_query(
        client, t, tipo="chart_bar",
        sql_texto="SELECT grupo AS label, valor FROM base",
        query_base_id=base["id"],
    )
    try:
        assert derivada["query_base_id"] == base["id"]
        buscada = client.get(f"/api/queries/{derivada['id']}", headers=_headers(t)).json()
        assert buscada["query_base_id"] == base["id"]
    finally:
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))


def test_base_inexistente_ou_inativa_e_rejeitada(client, auth_token):
    t = auth_token
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_base_inexistente", "nome": "Q",
            "sql_texto": "SELECT 1 FROM base", "tipo": "table",
            "query_base_id": 999999,
        },
        headers=_headers(t),
    )
    assert res.status_code == 400


def test_base_que_ja_e_derivada_e_rejeitada(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, sql_texto="SELECT 1 AS valor")
    derivada1 = _criar_query(client, t, sql_texto="SELECT valor FROM base", query_base_id=base["id"])
    try:
        res = client.post(
            "/api/queries/",
            json={
                "slug": "teste_encadeamento", "nome": "Q",
                "sql_texto": "SELECT valor FROM base", "tipo": "table",
                "query_base_id": derivada1["id"],
            },
            headers=_headers(t),
        )
        assert res.status_code == 400
        assert "encadear" in res.json()["detail"].lower()
    finally:
        client.delete(f"/api/queries/{derivada1['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))


def test_query_nao_pode_ser_base_de_si_mesma_no_patch(client, auth_token):
    t = auth_token
    query = _criar_query(client, t)
    try:
        res = client.patch(
            f"/api/queries/{query['id']}",
            json={"query_base_id": query["id"]},
            headers=_headers(t),
        )
        assert res.status_code == 400
    finally:
        client.delete(f"/api/queries/{query['id']}", headers=_headers(t))


def test_editar_sql_da_base_invalida_cache_das_derivadas(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, sql_texto="SELECT 1 AS grupo, 10 AS valor")
    derivada = _criar_query(
        client, t, tipo="table", cache_ttl=300,
        sql_texto="SELECT grupo, valor FROM base",
        query_base_id=base["id"],
    )
    try:
        primeiro = client.get(f"/api/queries/executar/{derivada['slug']}", headers=_headers(t)).json()
        assert primeiro["data"] == [{"grupo": 1, "valor": 10}]
        assert primeiro["from_cache"] is False

        # confirma que ficou em cache
        segundo = client.get(f"/api/queries/executar/{derivada['slug']}", headers=_headers(t)).json()
        assert segundo["from_cache"] is True

        # muda o SQL da base
        client.patch(
            f"/api/queries/{base['id']}",
            json={"sql_texto": "SELECT 1 AS grupo, 99 AS valor"},
            headers=_headers(t),
        )

        terceiro = client.get(f"/api/queries/executar/{derivada['slug']}", headers=_headers(t)).json()
        assert terceiro["from_cache"] is False
        assert terceiro["data"] == [{"grupo": 1, "valor": 99}]
    finally:
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))


def test_duplicar_derivada_preserva_query_base_id(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, sql_texto="SELECT 1 AS valor")
    derivada = _criar_query(client, t, sql_texto="SELECT valor FROM base", query_base_id=base["id"])
    copia = None
    try:
        res = client.post(f"/api/queries/{derivada['id']}/duplicar", headers=_headers(t))
        assert res.status_code == 200
        copia = res.json()
        assert copia["query_base_id"] == base["id"]
    finally:
        if copia:
            client.delete(f"/api/queries/{copia['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))


def test_testar_query_com_base_compoe_cte(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, sql_texto="SELECT 1 AS grupo, 10 AS valor")
    try:
        res = client.post(
            "/api/queries/testar",
            json={
                "slug": "teste_testar_com_base", "nome": "Q",
                "sql_texto": "SELECT grupo, valor FROM base", "tipo": "table",
                "query_base_id": base["id"],
            },
            headers=_headers(t),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["amostra"] == [{"grupo": 1, "valor": 10}]
    finally:
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))
