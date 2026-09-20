import uuid
from conftest import hard_delete_painel

PIVOT_SQL = (
    "SELECT 'Ficha A' AS ficha, 'Pergunta 1' AS pergunta, 'JAN/2026' AS mes, 202601 AS mes_ord, 1 AS qtd"
)


def _h(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def _criar(client, auth_token, slug, **overrides):
    return client.post(
        "/api/queries/",
        json={
            "slug": slug,
            "nome": "Teste Pivot",
            "sql_texto": PIVOT_SQL,
            "tipo": "table_dynamic",
            "cache_ttl": 0,
            **overrides,
        },
        headers=_h(auth_token),
    )


def _apagar(client, auth_token, query_id):
    client.delete(f"/api/queries/{query_id}", headers=_h(auth_token))


def test_criar_query_usa_defaults_de_pivot(client, auth_token):
    res = _criar(client, auth_token, f"teste_pivot_default_{uuid.uuid4().hex[:6]}")
    assert res.status_code == 200
    body = res.json()
    assert body["pivot_coluna"] is None
    assert body["pivot_ordem_coluna"] is None
    assert body["pivot_total"] is False
    _apagar(client, auth_token, body["id"])


def test_criar_query_com_pivot(client, auth_token):
    res = _criar(
        client, auth_token, f"teste_pivot_custom_{uuid.uuid4().hex[:6]}",
        pivot_coluna="mes", pivot_ordem_coluna="mes_ord", pivot_total=True,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["pivot_coluna"] == "mes"
    assert body["pivot_ordem_coluna"] == "mes_ord"
    assert body["pivot_total"] is True
    _apagar(client, auth_token, body["id"])


def test_atualizar_pivot_via_patch(client, auth_token):
    query = _criar(client, auth_token, f"teste_pivot_patch_{uuid.uuid4().hex[:6]}").json()
    res = client.patch(
        f"/api/queries/{query['id']}",
        json={"pivot_coluna": "mes", "pivot_ordem_coluna": "mes_ord", "pivot_total": True},
        headers=_h(auth_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["pivot_coluna"], body["pivot_ordem_coluna"], body["pivot_total"]) == ("mes", "mes_ord", True)
    _apagar(client, auth_token, query["id"])


def test_patch_string_vazia_limpa_o_pivot(client, auth_token):
    """PATCH ignora None (exclude_none), então o frontend limpa com ''. O
    backend normaliza '' pra NULL pra não deixar coluna-fantasma no banco."""
    query = _criar(
        client, auth_token, f"teste_pivot_limpar_{uuid.uuid4().hex[:6]}",
        pivot_coluna="mes", pivot_ordem_coluna="mes_ord", pivot_total=True,
    ).json()
    res = client.patch(
        f"/api/queries/{query['id']}",
        json={"pivot_coluna": "", "pivot_ordem_coluna": ""},
        headers=_h(auth_token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["pivot_coluna"] is None
    assert body["pivot_ordem_coluna"] is None
    _apagar(client, auth_token, query["id"])


def test_duplicar_query_preserva_pivot(client, auth_token):
    query = _criar(
        client, auth_token, f"teste_pivot_dup_{uuid.uuid4().hex[:6]}",
        pivot_coluna="mes", pivot_ordem_coluna="mes_ord", pivot_total=True,
    ).json()
    res = client.post(f"/api/queries/{query['id']}/duplicar", headers=_h(auth_token))
    assert res.status_code == 200
    copia = res.json()
    assert (copia["pivot_coluna"], copia["pivot_ordem_coluna"], copia["pivot_total"]) == ("mes", "mes_ord", True)
    _apagar(client, auth_token, copia["id"])
    _apagar(client, auth_token, query["id"])


def test_renderizar_painel_anexa_pivot_de_table_dynamic(client, auth_token):
    query_slug = f"query_pivot_{uuid.uuid4().hex[:8]}"
    query = _criar(
        client, auth_token, query_slug,
        pivot_coluna="mes", pivot_ordem_coluna="mes_ord", pivot_total=True,
    ).json()
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": f"painel_pivot_{uuid.uuid4().hex[:8]}", "nome": "Painel Pivot"},
        headers=_h(auth_token),
    ).json()["id"]
    try:
        client.put(
            f"/api/paineis/{painel_id}/indicadores",
            json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
            headers=_h(auth_token),
        )
        res = client.get(f"/api/paineis/{painel_id}/renderizar", headers=_h(auth_token))
        assert res.status_code == 200
        ind = res.json()["indicadores"][0]
        assert ind["pivot"] == {"coluna": "mes", "ordem_coluna": "mes_ord", "total": True}
    finally:
        hard_delete_painel(painel_id)
        _apagar(client, auth_token, query["id"])
