# Portabilidade de Painéis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exportar um painel para um arquivo `.json` autocontido (com suas queries, subqueries e variáveis) e importá-lo em outro ambiente com uma tela de pré-visualização que deixa o operador escolher item a item o que criar/sobrescrever.

**Architecture:** Um serviço de serialização (`backend/services/portabilidade.py`) converte painel + fecho transitivo de dependências em um dict de chaves naturais (slugs, nunca ids). Três endpoints admin em `backend/routes/portabilidade.py`: exportar (download), analisar (diff sem gravar) e importar (upsert seletivo dentro de uma transação). Frontend: botão de exportar na lista de painéis + página nova de importação.

**Tech Stack:** FastAPI, asyncpg (banco meta Postgres), SvelteKit (Svelte 5), pytest com `TestClient`.

**Spec:** `docs/superpowers/specs/2026-09-10-portabilidade-paineis-design.md`

## Global Constraints

- **Nenhum id numérico é serializado.** Chaves naturais entre ambientes: `paineis.slug` (UNIQUE global), `variaveis.slug` (UNIQUE global), `queries` por `(slug, empresa_id)` — para o caso global (`empresa_id IS NULL`) use `empresa_id IS NOT DISTINCT FROM $x`, porque o `UNIQUE (slug, empresa_id)` **não** captura duplicatas quando `empresa_id` é NULL (o código existente em `routes/queries.py` já usa esse padrão).
- **Todos os endpoints** usam `Depends(require_admin)` (de `middleware.auth`).
- **Campos de config são listados explicitamente** — nunca `SELECT *` no que vai pro JSON — para não vazar `id`, `criado_em`, `atualizado_em`, `grupo_id`, `empresa_id`, `subquery_id`, `kpi_imagem`/`imagem` crus.
- `empresa_slug` no import: `null` → global; slug conhecido no destino → id do destino; slug desconhecido → importa como global + aviso.
- `painel_usuarios` **nunca** é exportado nem importado.
- Imagens (`paineis.imagem`, `queries.kpi_imagem`) vão em base64 no arquivo.
- `formato` deve ser `"datahub-painel"` e `versao` ≤ `1`; caso contrário `400`.
- Testes seguem o padrão da suíte: `TestClient` contra o banco meta de dev, limpeza com `hard_delete_*` do `conftest.py` no `finally`. Queries de teste são removidas de verdade por `DELETE /api/queries/{id}` (é hard-delete).
- Commits frequentes, um por task no mínimo. Mensagens em português, prefixo `feat:` / `refactor:` / `test:`.
- Atribuição no final de cada commit:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs
  ```

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/services/grupos.py` | **novo** — `resolver_grupo_id(tabela, nome, conn=None)` compartilhado (hoje duplicado em `queries.py` e `paineis.py`). |
| `backend/routes/queries.py` | **modificar** — remove `_resolver_grupo_id` local, chama o compartilhado. |
| `backend/routes/paineis.py` | **modificar** — idem. |
| `backend/config/databases.py` | **modificar** — adiciona `meta_tx()` (context manager de transação na conexão meta). |
| `backend/services/portabilidade.py` | **novo** — constantes de campos, serializadores (`_serializar_query`, `_serializar_variavel`, `_serializar_painel`), `montar_bundle_painel`, `analisar_bundle`, `importar_bundle`, `validar_formato`. |
| `backend/routes/portabilidade.py` | **novo** — 3 endpoints. |
| `backend/main.py` | **modificar** — registra o router. |
| `frontend/src/lib/api.js` | **modificar** — `exportarPainel`, `analisarImportPainel`, `importarPainel`. |
| `frontend/src/routes/configuracoes/paineis/+page.svelte` | **modificar** — botão "Exportar" por card + link "Importar painel". |
| `frontend/src/routes/configuracoes/paineis/importar/+page.svelte` | **novo** — tela de importação. |
| `backend/tests/test_portabilidade_paineis.py` | **novo** — testes de export, analisar e importar. |

---

## Task 1: Helper de grupo compartilhado

**Files:**
- Create: `backend/services/grupos.py`
- Modify: `backend/routes/queries.py` (remove `_resolver_grupo_id` nas linhas ~131-141; troca as 2 chamadas)
- Modify: `backend/routes/paineis.py` (remove `_resolver_grupo_id` nas linhas ~65-76; troca as 2 chamadas)
- Test: `backend/tests/test_portabilidade_paineis.py` (só o teste desta task por enquanto)

**Interfaces:**
- Produces: `async def resolver_grupo_id(tabela: str, nome: str | None, conn=None) -> int | None`
  - `tabela` ∈ `{"query_grupos", "painel_grupos"}` (literal fixo no código).
  - `conn`: se passado, é uma conexão asyncpg (usada dentro de transação); se `None`, usa o pool via `query_meta`.
  - Retorna o id do grupo (achado por nome case-insensitive ou recém-criado), ou `None` se `nome` vazio.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_portabilidade_paineis.py`:

```python
import uuid
import pytest
from conftest import _connect_meta
import asyncio

from services.grupos import resolver_grupo_id


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_resolver_grupo_id_acha_ou_cria_e_reusa():
    nome = f"Grupo Teste {uuid.uuid4().hex[:8]}"

    async def cenario():
        id1 = await resolver_grupo_id("painel_grupos", nome)
        id2 = await resolver_grupo_id("painel_grupos", nome.upper())  # case-insensitive
        vazio = await resolver_grupo_id("painel_grupos", "  ")
        return id1, id2, vazio

    id1, id2, vazio = asyncio.run(cenario())
    assert id1 is not None
    assert id1 == id2
    assert vazio is None

    async def limpa():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM painel_grupos WHERE id = $1", id1)
        finally:
            await conn.close()
    asyncio.run(limpa())


def test_resolver_grupo_id_rejeita_tabela_desconhecida():
    with pytest.raises(ValueError):
        asyncio.run(resolver_grupo_id("usuarios", "x"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.grupos'`

- [ ] **Step 3: Write `backend/services/grupos.py`**

```python
from config.databases import query_meta

_TABELAS_PERMITIDAS = {"query_grupos", "painel_grupos"}


async def resolver_grupo_id(tabela: str, nome, conn=None):
    """Acha o grupo pelo nome (case-insensitive) ou cria um novo. `tabela` é
    um literal fixo do código (query_grupos | painel_grupos), nunca entrada
    de usuário. `conn`, se passado, roda dentro da transação chamadora."""
    if tabela not in _TABELAS_PERMITIDAS:
        raise ValueError(f"Tabela de grupo inválida: {tabela}")

    nome = (nome or "").strip()
    if not nome:
        return None

    exec_ = conn.fetch if conn is not None else query_meta
    existente = await exec_(f"SELECT id FROM {tabela} WHERE LOWER(nome) = LOWER($1)", nome)
    if existente:
        return existente[0]["id"]
    novo = await exec_(f"INSERT INTO {tabela} (nome) VALUES ($1) RETURNING id", nome)
    return novo[0]["id"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Refatorar `backend/routes/queries.py`**

Remover a função `_resolver_grupo_id` (linhas ~131-141). No topo, adicionar import:

```python
from services.grupos import resolver_grupo_id
```

Trocar as 2 chamadas `await _resolver_grupo_id(body.grupo_nome)` /
`await _resolver_grupo_id(grupo_nome)` por
`await resolver_grupo_id("query_grupos", body.grupo_nome)` e
`await resolver_grupo_id("query_grupos", grupo_nome)`.

- [ ] **Step 6: Refatorar `backend/routes/paineis.py`**

Remover a função `_resolver_grupo_id` (linhas ~65-76). Adicionar import:

```python
from services.grupos import resolver_grupo_id
```

Trocar as 2 chamadas por `await resolver_grupo_id("painel_grupos", body.grupo_nome)` e
`await resolver_grupo_id("painel_grupos", body.pop("grupo_nome"))`.

- [ ] **Step 7: Rodar a suíte de queries e paineis pra garantir que nada quebrou**

Run: `cd backend && pytest tests/test_queries_chart_config.py tests/test_paineis_meta.py tests/test_portabilidade_paineis.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/grupos.py backend/routes/queries.py backend/routes/paineis.py backend/tests/test_portabilidade_paineis.py
git commit -m "refactor: extrai resolver_grupo_id pra services/grupos.py compartilhado

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Task 2: Serialização + endpoint de exportação

**Files:**
- Create: `backend/services/portabilidade.py`
- Create: `backend/routes/portabilidade.py`
- Modify: `backend/main.py` (import + `include_router`)
- Modify: `frontend/src/lib/api.js` (`exportarPainel`)
- Test: `backend/tests/test_portabilidade_paineis.py`

**Interfaces:**
- Consumes: `resolver_grupo_id` (Task 1) — não usado ainda no export, mas o módulo importa constantes daqui nas próximas tasks.
- Produces:
  - `FORMATO = "datahub-painel"`, `VERSAO = 1`
  - `QUERY_CAMPOS`, `VARIAVEL_CAMPOS`, `PAINEL_CAMPOS`, `INDICADOR_CAMPOS`, `PAINEL_VARIAVEL_CAMPOS` (listas de str)
  - `def _serializar_variavel(row: dict) -> dict`
  - `async def _serializar_query(row: dict) -> dict` — `row` é uma linha `SELECT * FROM queries`; carrega tabelas-filhas
  - `async def _serializar_painel(row: dict) -> dict` — `row` é `SELECT * FROM paineis`; carrega indicadores + painel_variaveis
  - `async def montar_bundle_painel(painel_id: int) -> dict | None` — bundle completo com `avisos`; `None` se painel não existe
  - Endpoint `GET /api/paineis/{painel_id}/exportar`
  - Frontend `api.exportarPainel(id)` — dispara download, sem retorno

- [ ] **Step 1: Write the failing test**

Adicionar em `backend/tests/test_portabilidade_paineis.py`:

```python
from conftest import hard_delete_painel, hard_delete_variavel


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _criar_query(client, token, **over):
    slug = over.pop("slug", f"q_{uuid.uuid4().hex[:8]}")
    body = {
        "slug": slug, "nome": over.pop("nome", "Q"),
        "sql_texto": over.pop("sql_texto", "SELECT 1 AS valor"),
        "tipo": over.pop("tipo", "kpi"), "cache_ttl": 0,
    }
    body.update(over)
    r = client.post("/api/queries/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _criar_variavel(client, token, **over):
    slug = over.pop("slug", f"v_{uuid.uuid4().hex[:8]}")
    body = {"slug": slug, "nome": "V", "tipo": "text"}
    body.update(over)
    r = client.post("/api/variaveis/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _criar_painel(client, token, **over):
    slug = over.pop("slug", f"p_{uuid.uuid4().hex[:8]}")
    body = {"slug": slug, "nome": "P"}
    body.update(over)
    r = client.post("/api/paineis/", json=body, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_exportar_traz_fecho_transitivo_de_subquery_e_variaveis(client, auth_token):
    t = auth_token
    var = _criar_variavel(client, t, tipo="text")
    sub = _criar_query(client, t, tipo="table", sql_texto="SELECT 2 AS valor")
    principal = _criar_query(client, t, tipo="table", subquery_id=sub["id"])
    # parâmetro da principal ligado à variável
    client.put(f"/api/queries/{principal['id']}/parametros",
               json=[{"nome": "p1", "tipo": "text", "variavel_id": var["id"]}],
               headers=_headers(t))
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": principal["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))

    try:
        r = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t))
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        b = r.json()
        assert b["formato"] == "datahub-painel"
        assert b["versao"] == 1
        query_slugs = {q["slug"] for q in b["queries"]}
        assert principal["slug"] in query_slugs
        assert sub["slug"] in query_slugs          # fecho transitivo
        assert {v["slug"] for v in b["variaveis"]} == {var["slug"]}
        pq = next(q for q in b["queries"] if q["slug"] == principal["slug"])
        assert pq["subquery_slug"] == sub["slug"]
        assert pq["parametros"][0]["variavel_slug"] == var["slug"]
        assert b["painel"]["indicadores"][0]["query_slug"] == principal["slug"]
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{principal['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{sub['id']}", headers=_headers(t))
        hard_delete_variavel(var["id"])


def test_exportar_avisa_indicador_com_query_inexistente(client, auth_token):
    t = auth_token
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": "nao_existe_xyz", "linha": 1, "coluna": 1}],
               headers=_headers(t))
    try:
        r = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t))
        assert r.status_code == 200, r.text
        b = r.json()
        assert any("nao_existe_xyz" in a for a in b["avisos"])
        assert b["queries"] == []
    finally:
        hard_delete_painel(painel["id"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k exportar -v`
Expected: FAIL — 404 (rota não existe)

- [ ] **Step 3: Write `backend/services/portabilidade.py`**

```python
import base64
from datetime import datetime, timezone

from fastapi import HTTPException

from config.databases import query_meta

FORMATO = "datahub-painel"
VERSAO = 1

QUERY_CAMPOS = [
    "slug", "nome", "descricao", "sql_texto", "tipo", "cache_ttl", "ativo",
    "kpi_cor_fonte", "kpi_cor_fundo", "mapa_camada",
    "chart_fonte_tamanho", "chart_truncar_label", "chart_truncar_tamanho", "chart_mostrar_valor",
    "chart_valor_label", "chart_rotulo_eixo", "chart_rotulo_valor",
    "impressao_habilitada", "impressao_caminho", "impressao_coluna",
    "meta_habilitada", "meta_coluna_valor", "meta_coluna_inicio", "meta_coluna_fim",
    "meta_cor_dentro", "meta_cor_fora",
    "pdf_orientacao", "kpi_imagem_habilitada", "kpi_imagem_posicao",
    "kpi_valor_primeiro", "chart_filtro_coluna",
]
VARIAVEL_CAMPOS = ["slug", "nome", "descricao", "tipo", "query_fonte", "param_names", "ativo"]
PAINEL_CAMPOS = [
    "slug", "nome", "descricao", "icone", "colunas", "linhas_fixas", "total_linhas",
    "ordem_menu", "impressao_orientacao", "ativo",
]
INDICADOR_CAMPOS = ["query_slug", "titulo", "linha", "coluna", "col_span", "row_span", "posicao"]
PAINEL_VARIAVEL_CAMPOS = [
    "obrigatorio", "valor_padrao", "valor_padrao_inicio", "valor_padrao_fim", "posicao",
]


def _b64(dados) -> str | None:
    return base64.b64encode(dados).decode() if dados else None


async def _nome_por_id(tabela: str, col: str, id_):
    if not id_:
        return None
    r = await query_meta(f"SELECT {col} FROM {tabela} WHERE id = $1", id_)
    return r[0][col] if r else None


def _serializar_variavel(row: dict) -> dict:
    out = {c: row[c] for c in VARIAVEL_CAMPOS}
    # asyncpg devolve param_names como list[str] ou None
    out["param_names"] = list(out["param_names"] or [])
    return out


async def _serializar_query(row: dict) -> dict:
    out = {c: row[c] for c in QUERY_CAMPOS}
    out["grupo_nome"] = await _nome_por_id("query_grupos", "nome", row["grupo_id"])
    out["empresa_slug"] = await _nome_por_id("empresas", "slug", row["empresa_id"])
    out["subquery_slug"] = await _nome_por_id("queries", "slug", row["subquery_id"])
    out["kpi_imagem_base64"] = _b64(row.get("kpi_imagem"))
    out["kpi_imagem_mime"] = row.get("kpi_imagem_mime")

    params = await query_meta(
        "SELECT p.nome, p.tipo, p.obrigatorio, p.valor_padrao, p.descricao, p.param_slot, "
        "       v.slug AS variavel_slug "
        "FROM query_parametros p LEFT JOIN variaveis v ON v.id = p.variavel_id "
        "WHERE p.query_id = $1 ORDER BY p.id",
        row["id"],
    )
    out["parametros"] = [dict(r) for r in params]
    out["agrupamentos"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna, ordem FROM query_agrupamentos WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    out["agregacoes"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna, funcao, label, ordem FROM query_agregacoes WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    out["subquery_parametros"] = [
        dict(r) for r in await query_meta(
            "SELECT coluna_origem, parametro_destino, ordem FROM query_subquery_parametros "
            "WHERE query_id = $1 ORDER BY ordem, id",
            row["id"])
    ]
    return out


async def _serializar_painel(row: dict) -> dict:
    out = {c: row[c] for c in PAINEL_CAMPOS}
    out["grupo_nome"] = await _nome_por_id("painel_grupos", "nome", row["grupo_id"])
    out["empresa_slug"] = await _nome_por_id("empresas", "slug", row["empresa_id"])
    out["imagem_base64"] = _b64(row.get("imagem"))
    out["imagem_mime"] = row.get("imagem_mime")

    indicadores = await query_meta(
        "SELECT pi.*, v.slug AS filtro_slug FROM painel_indicadores pi "
        "LEFT JOIN variaveis v ON v.id = pi.filtro_clique_variavel_id "
        "WHERE pi.painel_id = $1 ORDER BY pi.linha, pi.coluna",
        row["id"],
    )
    out["indicadores"] = [
        {**{c: r[c] for c in INDICADOR_CAMPOS}, "filtro_clique_variavel_slug": r["filtro_slug"]}
        for r in indicadores
    ]

    pv = await query_meta(
        "SELECT pv.*, v.slug AS variavel_slug FROM painel_variaveis pv "
        "JOIN variaveis v ON v.id = pv.variavel_id "
        "WHERE pv.painel_id = $1 ORDER BY pv.posicao, pv.id",
        row["id"],
    )
    out["variaveis_painel"] = [
        {**{c: r[c] for c in PAINEL_VARIAVEL_CAMPOS}, "variavel_slug": r["variavel_slug"]}
        for r in pv
    ]
    return out


async def montar_bundle_painel(painel_id: int):
    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        return None
    p = dict(painel_rows[0])
    avisos: list[str] = []

    indicadores = await query_meta(
        "SELECT query_slug FROM painel_indicadores WHERE painel_id = $1", painel_id
    )

    # --- fecho transitivo de queries ---
    visitados: dict[str, dict | None] = {}
    fila = [r["query_slug"] for r in indicadores]
    while fila:
        slug = fila.pop()
        if slug in visitados:
            continue
        qr = await query_meta(
            "SELECT * FROM queries WHERE slug = $1 ORDER BY empresa_id NULLS FIRST LIMIT 1", slug
        )
        if not qr:
            avisos.append(f"Indicador referencia query inexistente: {slug}")
            visitados[slug] = None
            continue
        rowq = dict(qr[0])
        visitados[slug] = rowq
        if rowq["subquery_id"]:
            sub = await query_meta("SELECT slug FROM queries WHERE id = $1", rowq["subquery_id"])
            if sub:
                fila.append(sub[0]["slug"])

    queries_reais = [r for r in visitados.values() if r]

    # --- variáveis referenciadas ---
    var_slugs: set[str] = set()
    pv = await query_meta(
        "SELECT v.slug FROM painel_variaveis pv JOIN variaveis v ON v.id = pv.variavel_id "
        "WHERE pv.painel_id = $1", painel_id)
    var_slugs.update(r["slug"] for r in pv)
    fc = await query_meta(
        "SELECT v.slug FROM painel_indicadores pi JOIN variaveis v ON v.id = pi.filtro_clique_variavel_id "
        "WHERE pi.painel_id = $1", painel_id)
    var_slugs.update(r["slug"] for r in fc)
    for rowq in queries_reais:
        qp = await query_meta(
            "SELECT v.slug FROM query_parametros p JOIN variaveis v ON v.id = p.variavel_id "
            "WHERE p.query_id = $1", rowq["id"])
        var_slugs.update(r["slug"] for r in qp)

    variaveis_out = []
    for slug in sorted(var_slugs):
        vr = await query_meta("SELECT * FROM variaveis WHERE slug = $1", slug)
        if vr:
            variaveis_out.append(_serializar_variavel(dict(vr[0])))

    queries_out = [await _serializar_query(r) for r in queries_reais]

    return {
        "formato": FORMATO,
        "versao": VERSAO,
        "exportado_em": datetime.now(timezone.utc).isoformat(),
        "painel": await _serializar_painel(p),
        "queries": queries_out,
        "variaveis": variaveis_out,
        "avisos": avisos,
    }


def validar_formato(bundle: dict) -> None:
    if not isinstance(bundle, dict) or bundle.get("formato") != FORMATO:
        raise HTTPException(400, "Arquivo não é um export de painel do DataHub")
    if not isinstance(bundle.get("versao"), int) or bundle["versao"] > VERSAO:
        raise HTTPException(400, f"Versão de formato não suportada (máx: {VERSAO})")
    for chave in ("painel", "queries", "variaveis"):
        if chave not in bundle:
            raise HTTPException(400, f"Arquivo incompleto: falta '{chave}'")
```

- [ ] **Step 4: Write `backend/routes/portabilidade.py`**

```python
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from middleware.auth import require_admin
from services.portabilidade import montar_bundle_painel

router = APIRouter(tags=["Portabilidade"])


@router.get("/api/paineis/{painel_id}/exportar")
async def exportar_painel(painel_id: int, user=Depends(require_admin)):
    bundle = await montar_bundle_painel(painel_id)
    if bundle is None:
        raise HTTPException(404, "Painel não encontrado")

    slug = bundle["painel"]["slug"]
    filename = f"painel-{slug}-{date.today():%Y%m%d}.json"
    corpo = json.dumps(bundle, ensure_ascii=False, default=str, indent=2)
    return Response(
        content=corpo,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 5: Registrar o router em `backend/main.py`**

Na linha de import dos routes, adicionar `portabilidade`:

```python
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios, variaveis, paineis, portabilidade
```

Depois de `app.include_router(paineis.router)`:

```python
app.include_router(portabilidade.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k exportar -v`
Expected: PASS (2 testes)

- [ ] **Step 7: Adicionar `exportarPainel` em `frontend/src/lib/api.js`**

No bloco `// Painéis`, depois de `desativarPainel`:

```javascript
    exportarPainel: async (id) => {
        const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
        const res = await fetch(`${BASE}/api/paineis/${id}/exportar`, {
            headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        });
        if (!res.ok) {
            const txt = await res.text();
            let msg; try { msg = JSON.parse(txt).detail || txt; } catch { msg = txt; }
            throw new Error(msg || `HTTP ${res.status}`);
        }
        const blob = await res.blob();
        const dispo = res.headers.get('Content-Disposition') || '';
        const m = dispo.match(/filename="(.+?)"/);
        const nome = m ? m[1] : `painel-${id}.json`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = nome;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    },
```

- [ ] **Step 8: Commit**

```bash
git add backend/services/portabilidade.py backend/routes/portabilidade.py backend/main.py frontend/src/lib/api.js backend/tests/test_portabilidade_paineis.py
git commit -m "feat: exportacao de painel com fecho transitivo de queries e variaveis

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Task 3: Endpoint de análise (diff sem gravar)

**Files:**
- Modify: `backend/services/portabilidade.py` (`analisar_bundle` + helpers de diff)
- Modify: `backend/routes/portabilidade.py` (`POST /api/portabilidade/paineis/analisar`)
- Modify: `frontend/src/lib/api.js` (`analisarImportPainel`)
- Test: `backend/tests/test_portabilidade_paineis.py`

**Interfaces:**
- Consumes: `_serializar_query`, `_serializar_variavel`, `_serializar_painel`, `validar_formato`, `QUERY_CAMPOS` etc. (Task 2)
- Produces:
  - `async def _empresa_id_de_slug(slug: str | None) -> int | None`
  - `async def analisar_bundle(bundle: dict) -> dict` — retorna
    `{"formato_ok": True, "plano": {"painel": {...}, "queries": [...], "variaveis": [...]}, "avisos": [...]}`
    onde cada item é `{"slug", "nome", "situacao": "novo"|"conflito"|"identico", "campos_diferentes": [str]}`
  - Endpoint `POST /api/portabilidade/paineis/analisar` (body = bundle cru)
  - Frontend `api.analisarImportPainel(bundle) -> Promise<plano>`

- [ ] **Step 1: Write the failing test**

Adicionar em `backend/tests/test_portabilidade_paineis.py`:

```python
def _exportar(client, token, painel_id):
    r = client.get(f"/api/paineis/{painel_id}/exportar", headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_analisar_classifica_novo_identico_e_conflito(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS valor")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    try:
        # tudo já existe e nada mudou -> identico
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        assert r.status_code == 200, r.text
        plano = r.json()["plano"]
        assert plano["painel"]["situacao"] == "identico"
        assert plano["queries"][0]["situacao"] == "identico"

        # mexe no sql_texto do bundle -> conflito em sql_texto
        bundle["queries"][0]["sql_texto"] = "SELECT 999 AS valor"
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        item = r.json()["plano"]["queries"][0]
        assert item["situacao"] == "conflito"
        assert "sql_texto" in item["campos_diferentes"]

        # slug de query inexistente -> novo
        bundle["queries"][0]["slug"] = "totalmente_nova_xyz"
        bundle["painel"]["indicadores"][0]["query_slug"] = "totalmente_nova_xyz"
        r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(t))
        assert r.json()["plano"]["queries"][0]["situacao"] == "novo"
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{q['id']}", headers=_headers(t))


def test_analisar_rejeita_formato_invalido(client, auth_token):
    r = client.post("/api/portabilidade/paineis/analisar",
                    json={"formato": "outra-coisa"}, headers=_headers(auth_token))
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k analisar -v`
Expected: FAIL — 404/405 (rota não existe)

- [ ] **Step 3: Adicionar diff + `analisar_bundle` em `backend/services/portabilidade.py`**

```python
# chaves comparadas por entidade (topo + arrays-filhos)
_PAINEL_DIFF_KEYS = PAINEL_CAMPOS + [
    "grupo_nome", "empresa_slug", "imagem_base64", "imagem_mime",
    "indicadores", "variaveis_painel",
]
_QUERY_DIFF_KEYS = QUERY_CAMPOS + [
    "grupo_nome", "empresa_slug", "subquery_slug", "kpi_imagem_base64", "kpi_imagem_mime",
    "parametros", "agrupamentos", "agregacoes", "subquery_parametros",
]
_VARIAVEL_DIFF_KEYS = VARIAVEL_CAMPOS


def _comparar(atual: dict, novo: dict, keys) -> list[str]:
    difs = []
    for k in keys:
        if atual.get(k) != novo.get(k):
            difs.append(k)
    return difs


async def _empresa_id_de_slug(slug):
    if not slug:
        return None
    r = await query_meta("SELECT id FROM empresas WHERE slug = $1", slug)
    return r[0]["id"] if r else None


async def _classificar_query(qb: dict) -> dict:
    emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
    existente = await query_meta(
        "SELECT * FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        qb["slug"], emp_id,
    )
    base = {"slug": qb["slug"], "nome": qb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = await _serializar_query(dict(existente[0]))
    difs = _comparar(atual, qb, _QUERY_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def _classificar_variavel(vb: dict) -> dict:
    existente = await query_meta("SELECT * FROM variaveis WHERE slug = $1", vb["slug"])
    base = {"slug": vb["slug"], "nome": vb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = _serializar_variavel(dict(existente[0]))
    difs = _comparar(atual, vb, _VARIAVEL_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def _classificar_painel(pb: dict) -> dict:
    existente = await query_meta("SELECT * FROM paineis WHERE slug = $1", pb["slug"])
    base = {"slug": pb["slug"], "nome": pb.get("nome")}
    if not existente:
        return {**base, "situacao": "novo", "campos_diferentes": []}
    atual = await _serializar_painel(dict(existente[0]))
    difs = _comparar(atual, pb, _PAINEL_DIFF_KEYS)
    return {**base, "situacao": "identico" if not difs else "conflito", "campos_diferentes": difs}


async def analisar_bundle(bundle: dict) -> dict:
    validar_formato(bundle)
    avisos: list[str] = []

    plano = {
        "painel": await _classificar_painel(bundle["painel"]),
        "queries": [await _classificar_query(q) for q in bundle["queries"]],
        "variaveis": [await _classificar_variavel(v) for v in bundle["variaveis"]],
    }

    # aviso: empresa_slug do bundle não existe no destino
    slugs_emp = {e for e in (
        [bundle["painel"].get("empresa_slug")] + [q.get("empresa_slug") for q in bundle["queries"]]
    ) if e}
    for s in sorted(slugs_emp):
        if await _empresa_id_de_slug(s) is None:
            avisos.append(f"Empresa '{s}' não existe no destino — entidade entrará como global")

    # aviso: dependência referenciada que não está no bundle e não existe no destino
    slugs_query_bundle = {q["slug"] for q in bundle["queries"]}
    for ind in bundle["painel"].get("indicadores", []):
        qs = ind["query_slug"]
        if qs not in slugs_query_bundle:
            existe = await query_meta("SELECT 1 FROM queries WHERE slug = $1", qs)
            if not existe:
                avisos.append(f"Dependência ausente: query '{qs}' não está no arquivo nem no destino")

    slugs_var_bundle = {v["slug"] for v in bundle["variaveis"]}
    refs_var = set()
    for ind in bundle["painel"].get("indicadores", []):
        if ind.get("filtro_clique_variavel_slug"):
            refs_var.add(ind["filtro_clique_variavel_slug"])
    for pv in bundle["painel"].get("variaveis_painel", []):
        refs_var.add(pv["variavel_slug"])
    for q in bundle["queries"]:
        for p in q.get("parametros", []):
            if p.get("variavel_slug"):
                refs_var.add(p["variavel_slug"])
    for vs in sorted(refs_var):
        if vs not in slugs_var_bundle:
            existe = await query_meta("SELECT 1 FROM variaveis WHERE slug = $1", vs)
            if not existe:
                avisos.append(f"Dependência ausente: variável '{vs}' não está no arquivo nem no destino")

    return {"formato_ok": True, "plano": plano, "avisos": avisos}
```

- [ ] **Step 4: Adicionar o endpoint em `backend/routes/portabilidade.py`**

```python
from services.portabilidade import analisar_bundle

@router.post("/api/portabilidade/paineis/analisar")
async def analisar_import_painel(bundle: dict, user=Depends(require_admin)):
    return await analisar_bundle(bundle)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k analisar -v`
Expected: PASS (2 testes)

- [ ] **Step 6: Adicionar `analisarImportPainel` em `frontend/src/lib/api.js`**

Depois de `exportarPainel`:

```javascript
    analisarImportPainel: (bundle) =>
        request('/api/portabilidade/paineis/analisar', { method: 'POST', body: JSON.stringify(bundle) }),
```

- [ ] **Step 7: Commit**

```bash
git add backend/services/portabilidade.py backend/routes/portabilidade.py frontend/src/lib/api.js backend/tests/test_portabilidade_paineis.py
git commit -m "feat: analise de import de painel (novo/conflito/identico por item)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Task 4: Endpoint de importação (upsert seletivo em transação)

**Files:**
- Modify: `backend/config/databases.py` (`meta_tx`)
- Modify: `backend/services/portabilidade.py` (`importar_bundle` + upserts)
- Modify: `backend/routes/portabilidade.py` (`POST /api/portabilidade/paineis/importar`)
- Modify: `frontend/src/lib/api.js` (`importarPainel`)
- Test: `backend/tests/test_portabilidade_paineis.py`

**Interfaces:**
- Consumes: `resolver_grupo_id` (Task 1), serializadores + constantes (Task 2), `_empresa_id_de_slug` (Task 3), `invalidar_cache_query` de `services.query_runner`.
- Produces:
  - `config.databases.meta_tx()` — async context manager que dá `conn` asyncpg dentro de `conn.transaction()`
  - `async def importar_bundle(bundle: dict, aplicar: dict) -> dict` — retorna
    `{"painel_slug": str, "aplicado": {"variaveis": int, "queries": int, "painel": bool}, "avisos": [str]}`;
    levanta `HTTPException(400, {...})` se faltar dependência.
  - Endpoint `POST /api/portabilidade/paineis/importar`, body
    `{"bundle": {...}, "aplicar": {"variaveis": [slug], "queries": [slug], "painel": bool}}`
  - Frontend `api.importarPainel({bundle, aplicar}) -> Promise<resultado>`

- [ ] **Step 1: Write the failing test**

Adicionar em `backend/tests/test_portabilidade_paineis.py`:

```python
def _analisar(client, token, bundle):
    r = client.post("/api/portabilidade/paineis/analisar", json=bundle, headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()


def _importar(client, token, bundle, aplicar):
    return client.post("/api/portabilidade/paineis/importar",
                       json={"bundle": bundle, "aplicar": aplicar}, headers=_headers(token))


def test_importar_respeita_lista_aplicar_e_cria_so_o_marcado(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    # apaga tudo do destino
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))

    novo_painel_id = None
    try:
        # aplicar só a query, não o painel
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        assert r.json()["aplicado"]["queries"] == 1
        criada = client.get("/api/queries/", headers=_headers(t)).json()
        assert any(x["slug"] == q["slug"] for x in criada)

        # agora aplicar o painel também
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": True})
        assert r.status_code == 200, r.text
        pl = client.get("/api/paineis/", headers=_headers(t)).json()
        alvo = next(x for x in pl if x["slug"] == bundle["painel"]["slug"])
        novo_painel_id = alvo["id"]
        inds = client.get(f"/api/paineis/{novo_painel_id}/indicadores", headers=_headers(t)).json()
        assert inds[0]["query_slug"] == q["slug"]
    finally:
        if novo_painel_id:
            hard_delete_painel(novo_painel_id)
        nova = client.get("/api/queries/", headers=_headers(t)).json()
        alvo = next((x for x in nova if x["slug"] == q["slug"]), None)
        if alvo:
            client.delete(f"/api/queries/{alvo['id']}", headers=_headers(t))


def test_importar_bloqueia_quando_dependencia_ausente(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))

    try:
        # aplicar o painel mas NÃO a query da qual ele depende, e a query não existe no destino
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [], "painel": True})
        assert r.status_code == 400
        assert q["slug"] in r.text
    finally:
        pl = client.get("/api/paineis/", headers=_headers(t)).json()
        alvo = next((x for x in pl if x["slug"] == bundle["painel"]["slug"]), None)
        if alvo:
            hard_delete_painel(alvo["id"])


def test_importar_sobrescreve_query_existente_com_conteudo_do_bundle(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS valor")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])

    try:
        # edita a query no destino
        client.patch(f"/api/queries/{q['id']}", json={"sql_texto": "SELECT 42 AS valor"}, headers=_headers(t))
        # reimporta o bundle original marcando a query
        r = _importar(client, t, bundle, {"variaveis": [], "queries": [q["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        atual = client.get(f"/api/queries/{q['id']}", headers=_headers(t)).json()
        assert atual["sql_texto"] == "SELECT 1 AS valor"
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{q['id']}", headers=_headers(t))


def test_importar_recursao_de_subquery_mutua(client, auth_token):
    t = auth_token
    a = _criar_query(client, t, tipo="table")
    b = _criar_query(client, t, tipo="table")
    client.patch(f"/api/queries/{a['id']}", json={"subquery_id": b["id"]}, headers=_headers(t))
    client.patch(f"/api/queries/{b['id']}", json={"subquery_id": a["id"]}, headers=_headers(t))
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": a["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{a['id']}", headers=_headers(t))
    client.delete(f"/api/queries/{b['id']}", headers=_headers(t))

    ids = []
    try:
        r = _importar(client, t, bundle,
                      {"variaveis": [], "queries": [a["slug"], b["slug"]], "painel": False})
        assert r.status_code == 200, r.text
        todas = client.get("/api/queries/", headers=_headers(t)).json()
        qa = next(x for x in todas if x["slug"] == a["slug"])
        qb = next(x for x in todas if x["slug"] == b["slug"])
        ids = [qa["id"], qb["id"]]
        assert qa["subquery_id"] == qb["id"]
        assert qb["subquery_id"] == qa["id"]
    finally:
        # quebra o ciclo antes de deletar
        for i in ids:
            client.patch(f"/api/queries/{i}", json={"subquery_id": None}, headers=_headers(t))
        for i in ids:
            client.delete(f"/api/queries/{i}", headers=_headers(t))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k importar -v`
Expected: FAIL — 404/405 (rota não existe)

- [ ] **Step 3: Adicionar `meta_tx` em `backend/config/databases.py`**

No topo, adicionar ao import: `from contextlib import asynccontextmanager`.
Depois de `query_meta`:

```python
@asynccontextmanager
async def meta_tx():
    """Conexão dedicada do pool meta dentro de uma transação — para
    operações multi-tabela que precisam ser atômicas (ex: importação)."""
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
```

- [ ] **Step 4: Adicionar `importar_bundle` + upserts em `backend/services/portabilidade.py`**

```python
from config.databases import meta_tx
from services.grupos import resolver_grupo_id
from services.query_runner import invalidar_cache_query


async def _checar_dependencias(bundle, aplicar_var, aplicar_qry, aplicar_pnl) -> list[str]:
    """Toda query/variável referenciada pelo que vai ser aplicado tem que já
    existir no destino OU estar na lista de aplicação."""
    faltando: list[str] = []

    async def query_ok(slug):
        if slug in aplicar_qry:
            return True
        return bool(await query_meta("SELECT 1 FROM queries WHERE slug = $1", slug))

    async def var_ok(slug):
        if slug in aplicar_var:
            return True
        return bool(await query_meta("SELECT 1 FROM variaveis WHERE slug = $1", slug))

    if aplicar_pnl:
        for ind in bundle["painel"].get("indicadores", []):
            if not await query_ok(ind["query_slug"]):
                faltando.append(f"query '{ind['query_slug']}'")
            fs = ind.get("filtro_clique_variavel_slug")
            if fs and not await var_ok(fs):
                faltando.append(f"variável '{fs}'")
        for pv in bundle["painel"].get("variaveis_painel", []):
            if not await var_ok(pv["variavel_slug"]):
                faltando.append(f"variável '{pv['variavel_slug']}'")

    for q in bundle["queries"]:
        if q["slug"] not in aplicar_qry:
            continue
        if q.get("subquery_slug") and not await query_ok(q["subquery_slug"]):
            faltando.append(f"subquery '{q['subquery_slug']}'")
        for p in q.get("parametros", []):
            if p.get("variavel_slug") and not await var_ok(p["variavel_slug"]):
                faltando.append(f"variável '{p['variavel_slug']}'")

    # dedup preservando ordem
    return list(dict.fromkeys(faltando))


async def _upsert_variavel(conn, vb: dict):
    existente = await conn.fetch("SELECT id FROM variaveis WHERE slug = $1", vb["slug"])
    campos = ["nome", "descricao", "tipo", "query_fonte", "param_names", "ativo"]
    vals = [vb.get("nome"), vb.get("descricao"), vb.get("tipo"),
            vb.get("query_fonte"), list(vb.get("param_names") or []), vb.get("ativo", True)]
    if existente:
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(campos))
        await conn.execute(f"UPDATE variaveis SET {sets} WHERE id = ${len(campos)+1}",
                           *vals, existente[0]["id"])
    else:
        await conn.execute(
            "INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, param_names, ativo) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            vb["slug"], *vals)


async def _upsert_query_base(conn, qb: dict):
    """Passo 1: cria/atualiza a query SEM subquery_id (resolvido no passo 2)."""
    emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
    grupo_id = await resolver_grupo_id("query_grupos", qb.get("grupo_nome"), conn=conn)
    img = base64.b64decode(qb["kpi_imagem_base64"]) if qb.get("kpi_imagem_base64") else None

    dados = {c: qb.get(c) for c in QUERY_CAMPOS}
    dados["empresa_id"] = emp_id
    dados["grupo_id"] = grupo_id
    dados["kpi_imagem"] = img
    dados["kpi_imagem_mime"] = qb.get("kpi_imagem_mime")

    existente = await conn.fetch(
        "SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        qb["slug"], emp_id)

    cols = list(dados.keys())
    if existente:
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        await conn.execute(f"UPDATE queries SET {sets} WHERE id = ${len(cols)+1}",
                           *[dados[c] for c in cols], existente[0]["id"])
    else:
        ph = ", ".join(f"${i+1}" for i in range(len(cols) + 1))
        await conn.execute(
            f"INSERT INTO queries (slug, {', '.join(cols)}) VALUES ({ph})",
            qb["slug"], *[dados[c] for c in cols])


async def _set_subquery(conn, slug: str, subquery_slug: str):
    sub = await conn.fetch("SELECT id FROM queries WHERE slug = $1 ORDER BY empresa_id NULLS FIRST LIMIT 1",
                           subquery_slug)
    sub_id = sub[0]["id"] if sub else None
    await conn.execute("UPDATE queries SET subquery_id = $1 WHERE slug = $2", sub_id, slug)


async def _id_query_por_slug(conn, slug: str, emp_slug):
    emp_id = await _empresa_id_de_slug(emp_slug)
    r = await conn.fetch("SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
                         slug, emp_id)
    return r[0]["id"] if r else None


async def _id_var_por_slug(conn, slug):
    if not slug:
        return None
    r = await conn.fetch("SELECT id FROM variaveis WHERE slug = $1", slug)
    return r[0]["id"] if r else None


async def _reinserir_filhas_query(conn, qb: dict):
    qid = await _id_query_por_slug(conn, qb["slug"], qb.get("empresa_slug"))
    for tabela in ("query_parametros", "query_agrupamentos", "query_agregacoes", "query_subquery_parametros"):
        await conn.execute(f"DELETE FROM {tabela} WHERE query_id = $1", qid)

    for p in qb.get("parametros", []):
        await conn.execute(
            "INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            qid, p["nome"], p.get("tipo", "text"), p.get("obrigatorio", False),
            p.get("valor_padrao"), p.get("descricao"),
            await _id_var_por_slug(conn, p.get("variavel_slug")), p.get("param_slot"))
    for a in qb.get("agrupamentos", []):
        await conn.execute("INSERT INTO query_agrupamentos (query_id, coluna, ordem) VALUES ($1,$2,$3)",
                           qid, a["coluna"], a.get("ordem", 0))
    for a in qb.get("agregacoes", []):
        await conn.execute("INSERT INTO query_agregacoes (query_id, coluna, funcao, label, ordem) VALUES ($1,$2,$3,$4,$5)",
                           qid, a["coluna"], a["funcao"], a.get("label"), a.get("ordem", 0))
    for s in qb.get("subquery_parametros", []):
        await conn.execute(
            "INSERT INTO query_subquery_parametros (query_id, coluna_origem, parametro_destino, ordem) VALUES ($1,$2,$3,$4)",
            qid, s["coluna_origem"], s["parametro_destino"], s.get("ordem", 0))


async def _upsert_painel(conn, pb: dict):
    emp_id = await _empresa_id_de_slug(pb.get("empresa_slug"))
    grupo_id = await resolver_grupo_id("painel_grupos", pb.get("grupo_nome"), conn=conn)
    img = base64.b64decode(pb["imagem_base64"]) if pb.get("imagem_base64") else None

    dados = {c: pb.get(c) for c in PAINEL_CAMPOS if c != "slug"}
    dados["empresa_id"] = emp_id
    dados["grupo_id"] = grupo_id
    dados["imagem"] = img
    dados["imagem_mime"] = pb.get("imagem_mime")
    cols = list(dados.keys())

    existente = await conn.fetch("SELECT id FROM paineis WHERE slug = $1", pb["slug"])
    if existente:
        pid = existente[0]["id"]
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        await conn.execute(f"UPDATE paineis SET {sets} WHERE id = ${len(cols)+1}",
                           *[dados[c] for c in cols], pid)
    else:
        ph = ", ".join(f"${i+1}" for i in range(len(cols) + 1))
        row = await conn.fetch(
            f"INSERT INTO paineis (slug, {', '.join(cols)}) VALUES ({ph}) RETURNING id",
            pb["slug"], *[dados[c] for c in cols])
        pid = row[0]["id"]

    await conn.execute("DELETE FROM painel_indicadores WHERE painel_id = $1", pid)
    for ind in pb.get("indicadores", []):
        await conn.execute(
            "INSERT INTO painel_indicadores "
            "(painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, filtro_clique_variavel_id) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            pid, ind["query_slug"], ind.get("titulo"), ind["linha"], ind["coluna"],
            ind.get("col_span", 1), ind.get("row_span", 1), ind.get("posicao", 0),
            await _id_var_por_slug(conn, ind.get("filtro_clique_variavel_slug")))

    await conn.execute("DELETE FROM painel_variaveis WHERE painel_id = $1", pid)
    for pv in pb.get("variaveis_painel", []):
        vid = await _id_var_por_slug(conn, pv["variavel_slug"])
        if vid is None:
            continue
        await conn.execute(
            "INSERT INTO painel_variaveis "
            "(painel_id, variavel_id, obrigatorio, valor_padrao, valor_padrao_inicio, valor_padrao_fim, posicao) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            pid, vid, pv.get("obrigatorio", False), pv.get("valor_padrao"),
            pv.get("valor_padrao_inicio"), pv.get("valor_padrao_fim"), pv.get("posicao", 0))


async def importar_bundle(bundle: dict, aplicar: dict) -> dict:
    validar_formato(bundle)
    aplicar_var = set(aplicar.get("variaveis", []))
    aplicar_qry = set(aplicar.get("queries", []))
    aplicar_pnl = bool(aplicar.get("painel"))

    faltando = await _checar_dependencias(bundle, aplicar_var, aplicar_qry, aplicar_pnl)
    if faltando:
        raise HTTPException(400, "Dependências ausentes (marque para importar): " + ", ".join(faltando))

    slugs_query_tocados: list[str] = []
    async with meta_tx() as conn:
        for vb in bundle["variaveis"]:
            if vb["slug"] in aplicar_var:
                await _upsert_variavel(conn, vb)

        for qb in bundle["queries"]:
            if qb["slug"] in aplicar_qry:
                await _upsert_query_base(conn, qb)
                slugs_query_tocados.append(qb["slug"])

        for qb in bundle["queries"]:
            if qb["slug"] in aplicar_qry and qb.get("subquery_slug"):
                await _set_subquery(conn, qb["slug"], qb["subquery_slug"])

        for qb in bundle["queries"]:
            if qb["slug"] in aplicar_qry:
                await _reinserir_filhas_query(conn, qb)

        if aplicar_pnl:
            await _upsert_painel(conn, bundle["painel"])

    for slug in slugs_query_tocados:
        await invalidar_cache_query(slug)

    return {
        "painel_slug": bundle["painel"]["slug"],
        "aplicado": {"variaveis": len(aplicar_var), "queries": len(aplicar_qry), "painel": aplicar_pnl},
        "avisos": [],
    }
```

- [ ] **Step 5: Adicionar o endpoint em `backend/routes/portabilidade.py`**

```python
from pydantic import BaseModel
from services.portabilidade import importar_bundle


class ImportarInput(BaseModel):
    bundle: dict
    aplicar: dict


@router.post("/api/portabilidade/paineis/importar")
async def importar_painel(body: ImportarInput, user=Depends(require_admin)):
    return await importar_bundle(body.bundle, body.aplicar)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -k importar -v`
Expected: PASS (4 testes)

- [ ] **Step 7: Rodar o arquivo inteiro**

Run: `cd backend && pytest tests/test_portabilidade_paineis.py -v`
Expected: PASS (todos)

- [ ] **Step 8: Adicionar `importarPainel` em `frontend/src/lib/api.js`**

Depois de `analisarImportPainel`:

```javascript
    importarPainel: (payload) =>
        request('/api/portabilidade/paineis/importar', { method: 'POST', body: JSON.stringify(payload) }),
```

- [ ] **Step 9: Commit**

```bash
git add backend/config/databases.py backend/services/portabilidade.py backend/routes/portabilidade.py frontend/src/lib/api.js backend/tests/test_portabilidade_paineis.py
git commit -m "feat: importacao seletiva de painel em transacao (upsert por slug)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Task 5: Frontend — botão exportar + link importar na lista

**Files:**
- Modify: `frontend/src/routes/configuracoes/paineis/+page.svelte`
- Verify: `cd frontend && npm run check`

**Interfaces:**
- Consumes: `api.exportarPainel(id)` (Task 2)

- [ ] **Step 1: Adicionar estado e handler no `<script>`**

Depois da função `desativar`:

```javascript
  let exportandoId = null;

  async function exportar(p) {
    exportandoId = p.id;
    try {
      await api.exportarPainel(p.id);
    } catch (e) {
      alert(`Falha ao exportar: ${e.message}`);
    } finally {
      exportandoId = null;
    }
  }
```

- [ ] **Step 2: Adicionar o link "Importar painel" no header**

Trocar o `.page-header`:

```svelte
  <div class="page-header">
    <h2>Painéis</h2>
    <div class="header-acoes">
      <a href="/configuracoes/paineis/importar" class="btn-ghost">Importar painel</a>
      <a href="/configuracoes/paineis/novo" class="btn-primary">+ Novo Painel</a>
    </div>
  </div>
```

E no `<style>`:

```css
.header-acoes { display: flex; gap: 8px; align-items: center; }
```

- [ ] **Step 3: Adicionar o botão "Exportar" em cada card**

No `.card-actions`, depois do link "Editar":

```svelte
            <button class="btn-ghost btn-sm" on:click={() => exportar(p)} disabled={exportandoId === p.id}>
              {exportandoId === p.id ? 'Exportando…' : 'Exportar'}
            </button>
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run check`
Expected: sem erros novos.

Verificação manual (se o ambiente estiver rodando): abrir `/configuracoes/paineis`, clicar "Exportar" num painel → baixa `painel-<slug>-<data>.json`; abrir o arquivo e conferir que tem `painel`, `queries`, `variaveis`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/configuracoes/paineis/+page.svelte
git commit -m "feat: botao exportar painel e link importar na lista de paineis

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Task 6: Frontend — página de importação

**Files:**
- Create: `frontend/src/routes/configuracoes/paineis/importar/+page.svelte`
- Verify: `cd frontend && npm run check`

**Interfaces:**
- Consumes: `api.analisarImportPainel(bundle)` (Task 3), `api.importarPainel({bundle, aplicar})` (Task 4)

- [ ] **Step 1: Criar `frontend/src/routes/configuracoes/paineis/importar/+page.svelte`**

```svelte
<script>
  import { api } from '$lib/api.js';

  let bundle = null;
  let plano = null;
  let avisos = [];
  let erro = null;
  let carregando = false;
  let resultado = null;

  // seleção: chave = "tipo:slug" ou "painel"
  let marcados = {};

  async function aoEscolherArquivo(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    erro = null; plano = null; resultado = null;
    try {
      const texto = await file.text();
      bundle = JSON.parse(texto);
    } catch {
      erro = 'Arquivo inválido: não é um JSON.';
      return;
    }
    carregando = true;
    try {
      const r = await api.analisarImportPainel(bundle);
      plano = r.plano;
      avisos = r.avisos || [];
      marcados = {};
      const pre = (item, chave) => { marcados[chave] = item.situacao !== 'identico'; };
      pre(plano.painel, 'painel');
      for (const q of plano.queries) pre(q, `queries:${q.slug}`);
      for (const v of plano.variaveis) pre(v, `variaveis:${v.slug}`);
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  async function aplicar() {
    erro = null; resultado = null;
    const aplicarPayload = {
      painel: !!marcados['painel'],
      queries: plano.queries.filter(q => marcados[`queries:${q.slug}`]).map(q => q.slug),
      variaveis: plano.variaveis.filter(v => marcados[`variaveis:${v.slug}`]).map(v => v.slug),
    };
    carregando = true;
    try {
      resultado = await api.importarPainel({ bundle, aplicar: aplicarPayload });
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  const cor = (s) => s === 'novo' ? 'novo' : s === 'conflito' ? 'conflito' : 'identico';
  const rotulo = (s) => s === 'novo' ? 'novo' : s === 'conflito' ? 'conflito' : 'idêntico';
</script>

<svelte:head><title>Importar painel — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Importar painel</h2>
    <a href="/configuracoes/paineis" class="btn-ghost">Voltar</a>
  </div>

  <input type="file" accept="application/json,.json" on:change={aoEscolherArquivo} />

  {#if carregando}<p class="muted">Processando…</p>{/if}
  {#if erro}<p class="error">{erro}</p>{/if}

  {#if avisos.length}
    <div class="avisos">
      <strong>Avisos:</strong>
      <ul>{#each avisos as a}<li>{a}</li>{/each}</ul>
    </div>
  {/if}

  {#if resultado}
    <div class="ok">
      Importado. Aplicado: {resultado.aplicado.variaveis} variáveis,
      {resultado.aplicado.queries} queries{resultado.aplicado.painel ? ', painel' : ''}.
      <a href="/configuracoes/paineis">Ver painéis</a>
    </div>
  {/if}

  {#if plano && !resultado}
    <table class="plano">
      <thead><tr><th></th><th>Tipo</th><th>Slug</th><th>Nome</th><th>Situação</th><th>Campos diferentes</th></tr></thead>
      <tbody>
        <tr>
          <td><input type="checkbox" bind:checked={marcados['painel']} disabled={plano.painel.situacao === 'identico'} /></td>
          <td>painel</td>
          <td><code>{plano.painel.slug}</code></td>
          <td>{plano.painel.nome}</td>
          <td><span class="badge {cor(plano.painel.situacao)}">{rotulo(plano.painel.situacao)}</span></td>
          <td class="muted">{plano.painel.campos_diferentes.join(', ')}</td>
        </tr>
        {#each plano.queries as q}
          <tr>
            <td><input type="checkbox" bind:checked={marcados[`queries:${q.slug}`]} disabled={q.situacao === 'identico'} /></td>
            <td>query</td>
            <td><code>{q.slug}</code></td>
            <td>{q.nome}</td>
            <td><span class="badge {cor(q.situacao)}">{rotulo(q.situacao)}</span></td>
            <td class="muted">{q.campos_diferentes.join(', ')}</td>
          </tr>
        {/each}
        {#each plano.variaveis as v}
          <tr>
            <td><input type="checkbox" bind:checked={marcados[`variaveis:${v.slug}`]} disabled={v.situacao === 'identico'} /></td>
            <td>variável</td>
            <td><code>{v.slug}</code></td>
            <td>{v.nome}</td>
            <td><span class="badge {cor(v.situacao)}">{rotulo(v.situacao)}</span></td>
            <td class="muted">{v.campos_diferentes.join(', ')}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <button class="btn-primary" on:click={aplicar} disabled={carregando}>Aplicar</button>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.muted { color: var(--muted); font-size: 12px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.avisos { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin: 16px 0; font-size: 13px; }
.avisos ul { margin: 6px 0 0 18px; }
.ok { background: #1a4731; color: #3fb950; border-radius: 6px; padding: 12px; margin: 16px 0; font-size: 13px; }
.plano { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
.plano th, .plano td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
.plano code { color: var(--accent-blue); font-family: var(--font-display); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.badge.novo { background: #1a4731; color: #3fb950; }
.badge.conflito { background: #4d3800; color: #d29922; }
.badge.identico { background: var(--surface2); color: var(--muted); }
</style>
```

- [ ] **Step 2: Verificar**

Run: `cd frontend && npm run check`
Expected: sem erros novos.

Verificação manual (se o ambiente estiver rodando): exportar um painel, ir em `/configuracoes/paineis/importar`, escolher o arquivo → aparece a tabela com tudo `idêntico`; editar o `nome` do painel no JSON e reimportar → linha do painel vira `conflito` com `nome` em campos diferentes; clicar Aplicar → mensagem de sucesso.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/configuracoes/paineis/importar/+page.svelte
git commit -m "feat: tela de importacao de painel com preview e selecao por item

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HmTww2jeQHfQMHXo1JhiDs"
```

---

## Self-Review

**1. Spec coverage:**

| Requisito do spec | Task |
|---|---|
| Formato de arquivo versionado (`formato`/`versao`) | Task 2 (`FORMATO`/`VERSAO`, `validar_formato`) |
| Chaves naturais, nenhum id serializado | Task 2 (serializadores usam slug/nome) |
| Fecho transitivo de subquery com proteção de ciclo | Task 2 (`montar_bundle_painel`, dict `visitados`) |
| Variáveis via painel_variaveis + filtro_clique + query_parametros | Task 2 (`var_slugs`) |
| Grupo por nome | Task 1 + Task 2/4 |
| `empresa_slug` null/conhecido/desconhecido | Task 2 (serializa), Task 3 (aviso), Task 4 (`_empresa_id_de_slug`) |
| Imagens em base64 | Task 2 (`_b64`), Task 4 (`base64.b64decode`) |
| `painel_usuarios` fora | Nunca referenciado — ok |
| Aviso de query quebrada no export | Task 2 (`avisos`) |
| `GET /api/paineis/{id}/exportar` download | Task 2 |
| `POST analisar` sem gravar, novo/conflito/identico + campos_diferentes | Task 3 |
| Avisos de empresa e dependência ausente no analisar | Task 3 |
| `POST importar` com `aplicar` seletivo | Task 4 |
| Integridade referencial → 400 | Task 4 (`_checar_dependencias`) |
| Ordem de gravação (var → query base → subquery → filhas → painel) | Task 4 (`importar_bundle`) |
| Transação | Task 4 (`meta_tx`) |
| Invalidação de cache pós-commit | Task 4 |
| Helper `resolver_grupo_id` compartilhado | Task 1 |
| Helper `meta_tx` | Task 4 |
| Frontend: exportar no card + link importar | Task 5 |
| Frontend: página de importação com preview e checkboxes | Task 6 |
| Testes: 7 cenários do spec | Task 1 (grupo), Task 2 (fecho, query quebrada), Task 3 (classificação, formato), Task 4 (aplicar, dependência, upsert, recursão) — nota: o cenário "rollback" do spec foi trocado por cobertura via transação + os testes de dependência/upsert; ver nota abaixo |

**Nota sobre o teste de rollback:** o spec lista um 7º cenário ("rollback deixa o banco intacto quando o passo 4 falha"). Testá-lo de forma determinística exige forçar um erro no meio da transação com dados controlados. Se o executor conseguir um gatilho limpo (ex: `painel.slug` com >100 chars estourando `VARCHAR(100)` **depois** de queries já aplicadas no mesmo request), adicionar:

```python
def test_importar_faz_rollback_quando_painel_falha(client, auth_token):
    t = auth_token
    q = _criar_query(client, t, tipo="table")
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": q["slug"], "linha": 1, "coluna": 1}], headers=_headers(t))
    bundle = _exportar(client, t, painel["id"])
    hard_delete_painel(painel["id"])
    client.delete(f"/api/queries/{q['id']}", headers=_headers(t))
    bundle["queries"][0]["slug"] = f"rollback_{uuid.uuid4().hex[:8]}"
    bundle["painel"]["indicadores"][0]["query_slug"] = bundle["queries"][0]["slug"]
    bundle["painel"]["slug"] = "x" * 250  # estoura VARCHAR(100) no passo do painel

    try:
        r = _importar(client, t, bundle,
                      {"variaveis": [], "queries": [bundle["queries"][0]["slug"]], "painel": True})
        assert r.status_code >= 400
        # a query NÃO deve ter sido criada (rollback)
        todas = client.get("/api/queries/", headers=_headers(t)).json()
        assert not any(x["slug"] == bundle["queries"][0]["slug"] for x in todas)
    finally:
        todas = client.get("/api/queries/", headers=_headers(t)).json()
        alvo = next((x for x in todas if x["slug"] == bundle["queries"][0]["slug"]), None)
        if alvo:
            client.delete(f"/api/queries/{alvo['id']}", headers=_headers(t))
```

**2. Placeholder scan:** Sem "TBD"/"TODO"/"handle edge cases". Todo passo de código tem bloco completo. As chamadas cross-task usam nomes definidos nas seções `Interfaces`.

**3. Type consistency:**
- `resolver_grupo_id(tabela, nome, conn=None)` — assinatura idêntica em Task 1 (def), Task 4 (chamada com `conn=conn`). ✔
- `_empresa_id_de_slug` — definida em Task 3, usada em Task 4. ✔
- `_serializar_query`/`_serializar_variavel`/`_serializar_painel` — definidas em Task 2, reusadas em Task 3. ✔
- `montar_bundle_painel` retorna dict com `avisos`; endpoint em Task 2 usa `bundle["painel"]["slug"]`. ✔
- Bundle shape do export (Task 2) === shape esperado pelo analisar/importar (Tasks 3/4): chaves `formato`, `versao`, `painel`, `queries`, `variaveis`, `avisos`; `painel.indicadores[].filtro_clique_variavel_slug`; `queries[].subquery_slug`, `queries[].parametros[].variavel_slug`. ✔
- Frontend `marcados` usa chaves `"painel"`, `"queries:<slug>"`, `"variaveis:<slug>"` de forma consistente entre pré-seleção e `aplicar()`. ✔
- `api.importarPainel` recebe `{bundle, aplicar}`; endpoint `ImportarInput` espera `bundle`+`aplicar`. ✔

Nenhum problema encontrado.
