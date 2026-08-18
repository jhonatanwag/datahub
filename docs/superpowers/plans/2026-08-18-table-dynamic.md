# Query tipo `table_dynamic` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um novo tipo de query `table_dynamic` que agrupa (em múltiplos níveis) o resultado plano de um SQL, mostra agregações (soma/contagem/média/mínimo/máximo) por grupo, e permite um botão "Ações" por linha de detalhe que chama uma subconsulta (query já cadastrada, de qualquer tipo) passando colunas da linha como parâmetros, exibindo o resultado num dialog.

**Architecture:** Backend continua genérico — `resolver_query` não muda sua lógica de execução (o SQL de `table_dynamic` devolve linhas planas, sem `GROUP BY`). Agrupamento/agregação/mapeamento de parâmetros da subconsulta são 3 novas tabelas filhas (mesmo padrão de `query_parametros`), expostas por 3 pares de endpoints novos e anexadas ao payload de `renderizar_painel` quando o indicador é `table_dynamic`. No frontend, um componente novo `DynamicTable.svelte` constrói a árvore de agrupamento em JS a partir do resultado plano, e um `Modal.svelte` novo (não existe nenhum modal no projeto ainda) reaproveita `DataTable`/`KPICard`/`ChartPanel`/`MapPanel` para renderizar o resultado da subconsulta conforme o `tipo` dela.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, asyncpg, PostgreSQL, pytest

**Spec:** `docs/superpowers/specs/2026-08-18-table-dynamic-design.md`

## Global Constraints

- Agrupamento e agregação são calculados no frontend sobre o resultado plano da query — sem exigir `GROUP BY` no SQL
- Múltiplos níveis de agrupamento (ordenados), múltiplas agregações por grupo (aparecem em qualquer nível da árvore), múltiplos mapeamentos coluna→parâmetro para a subconsulta
- Subconsulta é uma query comum já cadastrada (qualquer `tipo`) — o `tipo` dela decide como o dialog renderiza, sem campo de tipo duplicado
- Uma subconsulta só por query `table_dynamic` (um botão "Ações" por linha, não vários)
- Sem paginação nem exportação CSV/Excel/PDF na `DynamicTable` — fica restrito ao `DataTable` tradicional
- Sem validação de que as colunas escolhidas (agrupamento/agregação/parâmetro) existem de fato no resultado — mesmo nível de confiança que `impressao_coluna` já aceita hoje (falha silenciosa)
- Sem sistema de migrations — `ALTER TABLE`/`CREATE TABLE` manual + refletir em `scripts/init-db.sql`, `scripts/init-meta-prod.sql` e README ("Deltas de schema pendentes")
- Frontend sem framework de testes — verificação manual via navegador

---

## Task 1: Schema — 3 tabelas novas + `queries.subquery_id`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`

**Interfaces:**
- Produces: tabelas `query_agrupamentos`, `query_agregacoes`, `query_subquery_parametros`; coluna `queries.subquery_id INTEGER REFERENCES queries(id)`.

- [ ] **Step 1: Aplicar no Postgres de dev**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
ALTER TABLE queries ADD COLUMN subquery_id INTEGER REFERENCES queries(id);

CREATE TABLE query_agrupamentos (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagrup_query_id ON query_agrupamentos(query_id);

CREATE TABLE query_agregacoes (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    funcao    VARCHAR(10) NOT NULL,
    label     TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagreg_query_id ON query_agregacoes(query_id);

CREATE TABLE query_subquery_parametros (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna_origem     TEXT NOT NULL,
    parametro_destino TEXT NOT NULL,
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qsqp_query_id ON query_subquery_parametros(query_id);
"
```

- [ ] **Step 2: Verificar que aplicou**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\d queries" | grep subquery_id
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\dt query_agrupamentos query_agregacoes query_subquery_parametros"
```

Expected: `subquery_id` aparece em `queries`; as 3 tabelas novas aparecem em `\dt`.

- [ ] **Step 3: Refletir em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`**

No bloco `CREATE TABLE queries`, logo após `meta_cor_fora TEXT DEFAULT '#f85149',` (e antes do `UNIQUE (slug, empresa_id)`), adicionar:

```sql
    subquery_id    INTEGER REFERENCES queries(id),
```

Logo após o bloco `CREATE TABLE query_parametros` (depois do `CREATE INDEX idx_qp_query_id ...`), adicionar as 3 tabelas novas (mesmo bloco do Step 1, sem o `ALTER TABLE` que já vai embutido no `CREATE TABLE queries`):

```sql
CREATE TABLE query_agrupamentos (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagrup_query_id ON query_agrupamentos(query_id);

CREATE TABLE query_agregacoes (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    funcao    VARCHAR(10) NOT NULL,
    label     TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagreg_query_id ON query_agregacoes(query_id);

CREATE TABLE query_subquery_parametros (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna_origem     TEXT NOT NULL,
    parametro_destino TEXT NOT NULL,
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qsqp_query_id ON query_subquery_parametros(query_id);
```

- [ ] **Step 4: Atualizar `README.md` — "Deltas de schema pendentes"**

No bloco de `SELECT column_name ... WHERE table_name = 'queries'` (linha ~120-122), adicionar `'subquery_id'` à lista de colunas verificadas:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'queries'
  AND column_name IN ('mapa_camada', 'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor', 'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna', 'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio', 'meta_coluna_fim', 'meta_cor_dentro', 'meta_cor_fora', 'subquery_id');
```

Adicionar uma nova checagem de tabela logo após o bloco de `SELECT`s existente:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('query_agrupamentos', 'query_agregacoes', 'query_subquery_parametros');
```

No bloco de `ALTER TABLE`s a aplicar (final da seção), adicionar:

```sql
-- 2026-08-18 — query tipo table_dynamic (agrupamento, agregação, subconsulta drill-down)
ALTER TABLE queries ADD COLUMN subquery_id INTEGER REFERENCES queries(id);

CREATE TABLE query_agrupamentos (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagrup_query_id ON query_agrupamentos(query_id);

CREATE TABLE query_agregacoes (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    funcao    VARCHAR(10) NOT NULL,
    label     TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagreg_query_id ON query_agregacoes(query_id);

CREATE TABLE query_subquery_parametros (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna_origem     TEXT NOT NULL,
    parametro_destino TEXT NOT NULL,
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qsqp_query_id ON query_subquery_parametros(query_id);
```

- [ ] **Step 5: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md
git commit -m "feat: add schema for table_dynamic query type (grouping, aggregation, subquery drill-down)"
```

---

## Task 2: Backend — `queries.py`: tipo, campo `subquery_id` e CRUD das 3 listas

**Files:**
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_queries_table_dynamic.py`

**Interfaces:**
- Consumes: schema do Task 1.
- Produces: `TIPOS_VALIDOS` inclui `'table_dynamic'`; `QueryInput`/`QueryUpdate.subquery_id`; `GET/PUT /api/queries/{id}/agrupamentos`; `GET/PUT /api/queries/{id}/agregacoes`; `GET/PUT /api/queries/{id}/subquery-parametros`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_queries_table_dynamic.py`:

```python
TABLE_DYNAMIC_SQL = "SELECT 'Fazenda Manga' AS fazenda, 'Equipamento 1' AS equipamento, 3 AS qtd"


def _criar_query_table_dynamic(client, auth_token, slug, subquery_id=None):
    res = client.post(
        "/api/queries/",
        json={
            "slug": slug,
            "nome": "Teste Table Dynamic",
            "sql_texto": TABLE_DYNAMIC_SQL,
            "tipo": "table_dynamic",
            "subquery_id": subquery_id,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    return res.json()


def test_criar_query_table_dynamic(client, auth_token):
    body = _criar_query_table_dynamic(client, auth_token, "teste_table_dynamic_criar")
    assert body["tipo"] == "table_dynamic"
    assert body["subquery_id"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_tipo_invalido_ainda_rejeitado(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_tipo_invalido",
            "nome": "Teste",
            "sql_texto": TABLE_DYNAMIC_SQL,
            "tipo": "nao_existe",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_agrupamentos_get_put_roundtrip(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agrupamentos")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agrupamentos",
            json=[
                {"coluna": "fazenda", "ordem": 0},
                {"coluna": "equipamento", "ordem": 1},
            ],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert [r["coluna"] for r in salvos] == ["fazenda", "equipamento"]

        get_res = client.get(
            f"/api/queries/{query['id']}/agrupamentos",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert [r["coluna"] for r in get_res.json()] == ["fazenda", "equipamento"]
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_agregacoes_get_put_roundtrip(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agregacoes")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agregacoes",
            json=[{"coluna": "qtd", "funcao": "soma", "label": "Total", "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert salvos[0]["coluna"] == "qtd"
        assert salvos[0]["funcao"] == "soma"
        assert salvos[0]["label"] == "Total"
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_agregacoes_funcao_invalida_rejeitada(client, auth_token):
    query = _criar_query_table_dynamic(client, auth_token, "teste_agregacoes_invalida")
    try:
        res = client.put(
            f"/api/queries/{query['id']}/agregacoes",
            json=[{"coluna": "qtd", "funcao": "mediana", "label": None, "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 400
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_subquery_parametros_get_put_roundtrip(client, auth_token):
    sub = client.post(
        "/api/queries/",
        json={
            "slug": "teste_subquery_alvo",
            "nome": "Subconsulta",
            "sql_texto": "SELECT 1 AS valor",
            "tipo": "kpi",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()
    query = _criar_query_table_dynamic(client, auth_token, "teste_subquery_parametros", subquery_id=sub["id"])
    try:
        res = client.put(
            f"/api/queries/{query['id']}/subquery-parametros",
            json=[{"coluna_origem": "equipamento", "parametro_destino": "prefixo", "ordem": 0}],
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        salvos = res.json()
        assert salvos[0]["coluna_origem"] == "equipamento"
        assert salvos[0]["parametro_destino"] == "prefixo"

        atualizada = client.get(
            f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"}
        ).json()
        assert atualizada["subquery_id"] == sub["id"]
    finally:
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        client.delete(f"/api/queries/{sub['id']}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_table_dynamic.py -v`
Expected: FAIL — `'table_dynamic'` não está em `TIPOS_VALIDOS` (erro 400 em toda criação), `subquery_id` não existe em `QueryInput`, e os 6 endpoints novos não existem (404).

- [ ] **Step 3: Implement — `backend/routes/queries.py`**

`TIPOS_VALIDOS` (linha 77-81):

```python
TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map', 'table_dynamic'
}

FUNCOES_AGREGACAO_VALIDAS = {'soma', 'contagem', 'media', 'minimo', 'maximo'}
```

`QueryInput`: adicionar após `testar_parametros`:

```python
    subquery_id: Optional[int] = None
```

`QueryUpdate`: adicionar após `meta_cor_fora`:

```python
    subquery_id: Optional[int] = None
```

Novos modelos, logo após `ParamInput`:

```python
class AgrupamentoInput(BaseModel):
    coluna: str
    ordem: int = 0


class AgregacaoInput(BaseModel):
    coluna: str
    funcao: str
    label: Optional[str] = None
    ordem: int = 0


class SubqueryParametroInput(BaseModel):
    coluna_origem: str
    parametro_destino: str
    ordem: int = 0
```

`ALLOWED_COLS` em `atualizar_query` (linha 284-291): adicionar `'subquery_id'` ao final do set.

`criar_query` — INSERT (linha 241-261) passa a ter 26 colunas; adicionar `subquery_id` ao final da lista de colunas, do `VALUES` (`$26`) e dos valores:

```python
        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor,
                chart_valor_label, impressao_habilitada, impressao_caminho, impressao_coluna,
                meta_habilitada, meta_coluna_valor, meta_coluna_inicio, meta_coluna_fim,
                meta_cor_dentro, meta_cor_fora, subquery_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo,
            body.kpi_cor_fonte, body.kpi_cor_fundo, body.mapa_camada,
            body.chart_fonte_tamanho, body.chart_truncar_label,
            body.chart_truncar_tamanho, body.chart_mostrar_valor,
            body.chart_valor_label, body.impressao_habilitada,
            body.impressao_caminho, body.impressao_coluna,
            body.meta_habilitada, body.meta_coluna_valor,
            body.meta_coluna_inicio, body.meta_coluna_fim,
            body.meta_cor_dentro, body.meta_cor_fora, body.subquery_id)
```

Novos endpoints, logo após `salvar_parametros` (linha 212), antes de `buscar_query`:

```python
@router.get("/{query_id}/agrupamentos")
async def listar_agrupamentos(query_id: int, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT * FROM query_agrupamentos WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar agrupamentos: {e}")


@router.put("/{query_id}/agrupamentos")
async def salvar_agrupamentos(
    query_id: int, agrupamentos: List[AgrupamentoInput], user=Depends(require_admin)
):
    try:
        await query_meta("DELETE FROM query_agrupamentos WHERE query_id = $1", query_id)
        for a in agrupamentos:
            await query_meta(
                "INSERT INTO query_agrupamentos (query_id, coluna, ordem) VALUES ($1, $2, $3)",
                query_id, a.coluna, a.ordem
            )
        rows = await query_meta(
            "SELECT * FROM query_agrupamentos WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar agrupamentos: {e}")


@router.get("/{query_id}/agregacoes")
async def listar_agregacoes(query_id: int, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT * FROM query_agregacoes WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar agregações: {e}")


@router.put("/{query_id}/agregacoes")
async def salvar_agregacoes(
    query_id: int, agregacoes: List[AgregacaoInput], user=Depends(require_admin)
):
    try:
        for a in agregacoes:
            if a.funcao not in FUNCOES_AGREGACAO_VALIDAS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Função de agregação inválida: {a.funcao}. Use: {FUNCOES_AGREGACAO_VALIDAS}"
                )
        await query_meta("DELETE FROM query_agregacoes WHERE query_id = $1", query_id)
        for a in agregacoes:
            await query_meta(
                "INSERT INTO query_agregacoes (query_id, coluna, funcao, label, ordem) VALUES ($1, $2, $3, $4, $5)",
                query_id, a.coluna, a.funcao, a.label, a.ordem
            )
        rows = await query_meta(
            "SELECT * FROM query_agregacoes WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar agregações: {e}")


@router.get("/{query_id}/subquery-parametros")
async def listar_subquery_parametros(query_id: int, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT * FROM query_subquery_parametros WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar parâmetros da subconsulta: {e}")


@router.put("/{query_id}/subquery-parametros")
async def salvar_subquery_parametros(
    query_id: int, parametros: List[SubqueryParametroInput], user=Depends(require_admin)
):
    try:
        await query_meta("DELETE FROM query_subquery_parametros WHERE query_id = $1", query_id)
        for p in parametros:
            await query_meta("""
                INSERT INTO query_subquery_parametros (query_id, coluna_origem, parametro_destino, ordem)
                VALUES ($1, $2, $3, $4)
            """, query_id, p.coluna_origem, p.parametro_destino, p.ordem)
        rows = await query_meta(
            "SELECT * FROM query_subquery_parametros WHERE query_id = $1 ORDER BY ordem", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar parâmetros da subconsulta: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_table_dynamic.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_queries_table_dynamic.py
git commit -m "feat: add table_dynamic query type with grouping/aggregation/subquery config endpoints"
```

---

## Task 3: Backend — `executar_query` passa a aceitar parâmetros

**Files:**
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_executar_query_parametrizada.py`

**Interfaces:**
- Consumes: `resolver_query` (já existente, `backend/services/query_runner.py:76`).
- Produces: `GET /api/queries/executar/{slug}?param1=valor1` passa a filtrar pelo parâmetro em vez de ignorá-lo.
- Independente do Task 2 — pode ser feito em paralelo.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_executar_query_parametrizada.py`:

```python
def test_executar_query_com_parametro_na_querystring_filtra_resultado(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_executar_parametrizada",
            "nome": "Teste Executar Parametrizada",
            "sql_texto": "SELECT $1::text AS valor_recebido",
            "tipo": "kpi",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]
    client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "meu_param", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            "/api/queries/executar/teste_executar_parametrizada?meu_param=abc123",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        assert res.json()["data"][0]["valor_recebido"] == "abc123"

        sem_param = client.get(
            "/api/queries/executar/teste_executar_parametrizada",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert sem_param.status_code == 200
        assert sem_param.json()["data"][0]["valor_recebido"] is None
    finally:
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec datahub_backend python -m pytest tests/test_executar_query_parametrizada.py -v`
Expected: FAIL — `assert 'abc123' == None`, já que `executar_query` hoje chama `resolver_query` sem `parametros`, então `meu_param` é ignorado mesmo estando na querystring.

- [ ] **Step 3: Implement — `backend/routes/queries.py`**

Adicionar `Request` ao import do topo do arquivo:

```python
from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, Request
```

`executar_query` (linha 110-121):

```python
@router.get("/executar/{slug}")
async def executar_query(slug: str, request: Request, user=Depends(get_current_user)):
    try:
        return await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"],
            parametros=dict(request.query_params)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar query: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec datahub_backend python -m pytest tests/test_executar_query_parametrizada.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam (nenhum outro caller de `executar_query` passava querystring antes, então nada deveria quebrar).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_executar_query_parametrizada.py
git commit -m "feat: forward query params to GET /api/queries/executar/{slug}"
```

---

## Task 4: Backend — `renderizar_painel` propaga config de `table_dynamic`

**Files:**
- Modify: `backend/routes/paineis.py`
- Test: `backend/tests/test_paineis_table_dynamic.py`

**Interfaces:**
- Consumes: schema do Task 1, endpoints do Task 2.
- Produces: cada indicador com `query_tipo == 'table_dynamic'` em `GET /api/paineis/{id}/renderizar` ganha `agrupamentos: string[]`, `agregacoes: [{coluna,funcao,label}]`, `subquery: {slug,tipo,parametros:[{coluna_origem,parametro_destino}]} | null`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_paineis_table_dynamic.py`:

```python
import uuid
from conftest import hard_delete_painel


def test_renderizar_painel_anexa_config_de_table_dynamic(client, auth_token):
    sub_slug = f"sub_{uuid.uuid4().hex[:8]}"
    sub = client.post(
        "/api/queries/",
        json={
            "slug": sub_slug,
            "nome": "Subconsulta KPI",
            "sql_texto": "SELECT 1 AS valor",
            "tipo": "kpi",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_dynamic_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Dynamic",
            "sql_texto": "SELECT 'Fazenda Manga' AS fazenda, 'Equip 1' AS equipamento, 3 AS qtd",
            "tipo": "table_dynamic",
            "cache_ttl": 0,
            "subquery_id": sub["id"],
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    client.put(
        f"/api/queries/{query['id']}/agrupamentos",
        json=[{"coluna": "fazenda", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/queries/{query['id']}/agregacoes",
        json=[{"coluna": "qtd", "funcao": "soma", "label": "Total", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/queries/{query['id']}/subquery-parametros",
        json=[{"coluna_origem": "equipamento", "parametro_destino": "prefixo", "ordem": 0}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    painel_slug = f"painel_dynamic_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Dynamic"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        ind = res.json()["indicadores"][0]
        assert ind["query_tipo"] == "table_dynamic"
        assert ind["agrupamentos"] == ["fazenda"]
        assert ind["agregacoes"] == [{"coluna": "qtd", "funcao": "soma", "label": "Total"}]
        assert ind["subquery"]["slug"] == sub_slug
        assert ind["subquery"]["tipo"] == "kpi"
        assert ind["subquery"]["parametros"] == [
            {"coluna_origem": "equipamento", "parametro_destino": "prefixo"}
        ]
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        client.delete(f"/api/queries/{sub['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_renderizar_painel_table_dynamic_sem_subquery_retorna_none(client, auth_token):
    query_slug = f"query_dynamic_sem_sub_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Dynamic Sem Subquery",
            "sql_texto": "SELECT 'Fazenda Manga' AS fazenda, 3 AS qtd",
            "tipo": "table_dynamic",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_dynamic_sem_sub_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Dynamic Sem Subquery"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        ind = res.json()["indicadores"][0]
        assert ind["subquery"] is None
        assert ind["agrupamentos"] == []
        assert ind["agregacoes"] == []
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_table_dynamic.py -v`
Expected: FAIL — `KeyError: 'agrupamentos'` (campos ainda não existem na resposta).

- [ ] **Step 3: Implement — `backend/routes/paineis.py`**

No `SELECT` de `renderizar_painel` (linha 380-390), adicionar `q.id AS query_id` e `q.subquery_id`:

```python
    indicadores = await query_meta("""
        SELECT pi.*, q.id AS query_id, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label, q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna,
               q.meta_habilitada, q.meta_coluna_valor, q.meta_coluna_inicio, q.meta_coluna_fim,
               q.meta_cor_dentro, q.meta_cor_fora, q.subquery_id
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
```

No loop (linha 392-409), depois de popular `ind_dict["erro"] = None` (dentro do `try`, ainda antes do `except`), adicionar:

```python
            if ind_dict["query_tipo"] == "table_dynamic":
                agrup_rows = await query_meta(
                    "SELECT coluna FROM query_agrupamentos WHERE query_id = $1 ORDER BY ordem",
                    ind_dict["query_id"]
                )
                ind_dict["agrupamentos"] = [r["coluna"] for r in agrup_rows]

                agreg_rows = await query_meta(
                    "SELECT coluna, funcao, label FROM query_agregacoes WHERE query_id = $1 ORDER BY ordem",
                    ind_dict["query_id"]
                )
                ind_dict["agregacoes"] = [dict(r) for r in agreg_rows]

                if ind_dict.get("subquery_id"):
                    sub_rows = await query_meta(
                        "SELECT slug, tipo FROM queries WHERE id = $1", ind_dict["subquery_id"]
                    )
                    param_rows = await query_meta("""
                        SELECT coluna_origem, parametro_destino
                        FROM query_subquery_parametros
                        WHERE query_id = $1 ORDER BY ordem
                    """, ind_dict["query_id"])
                    ind_dict["subquery"] = {
                        "slug": sub_rows[0]["slug"],
                        "tipo": sub_rows[0]["tipo"],
                        "parametros": [dict(r) for r in param_rows]
                    } if sub_rows else None
                else:
                    ind_dict["subquery"] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_table_dynamic.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam — `q.id AS query_id` é uma coluna nova, não deve colidir com `pi.id` (que continua vindo de `pi.*`) nem afetar indicadores de outros tipos (o bloco novo só roda quando `query_tipo == "table_dynamic"`).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/paineis.py backend/tests/test_paineis_table_dynamic.py
git commit -m "feat: attach grouping/aggregation/subquery config to table_dynamic indicators in renderizar_painel"
```

---

## Task 5: Frontend — `api.js`

**Files:**
- Modify: `frontend/src/lib/api.js`

**Interfaces:**
- Consumes: endpoints do Task 2.
- Produces: `api.agrupamentosQuery`, `api.salvarAgrupamentosQuery`, `api.agregacoesQuery`, `api.salvarAgregacoesQuery`, `api.subqueryParametrosQuery`, `api.salvarSubqueryParametrosQuery`.
- Sem testes automatizados — projeto não tem framework de teste de frontend; validado indiretamente pelos testes de backend (Task 2) e pela verificação manual do Task 8.

- [ ] **Step 1: Implement**

Logo após `salvarParametrosQuery` (linha 71), adicionar:

```js
    agrupamentosQuery:             (id)    => request(`/api/queries/${id}/agrupamentos`),
    salvarAgrupamentosQuery:       (id, d) => request(`/api/queries/${id}/agrupamentos`, { method: 'PUT', body: JSON.stringify(d) }),
    agregacoesQuery:               (id)    => request(`/api/queries/${id}/agregacoes`),
    salvarAgregacoesQuery:         (id, d) => request(`/api/queries/${id}/agregacoes`, { method: 'PUT', body: JSON.stringify(d) }),
    subqueryParametrosQuery:       (id)    => request(`/api/queries/${id}/subquery-parametros`),
    salvarSubqueryParametrosQuery: (id, d) => request(`/api/queries/${id}/subquery-parametros`, { method: 'PUT', body: JSON.stringify(d) }),
```

- [ ] **Step 2: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Verificação manual rápida**

No console do navegador (com sessão logada em `http://localhost:3000`), confirmar que as funções existem:

```js
// DevTools console, na aba do app
import('/src/lib/api.js').then(m => console.log(typeof m.api.agrupamentosQuery, typeof m.api.salvarAgregacoesQuery))
// Esperado: "function function"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.js
git commit -m "feat: add api.js helpers for table_dynamic grouping/aggregation/subquery config"
```

---

## Task 6: Frontend — `Modal.svelte` (novo)

**Files:**
- Create: `frontend/src/lib/components/Modal.svelte`

**Interfaces:**
- Produces: componente `Modal` com props `aberto: boolean`, `onClose: () => void`, e um `<slot />` para o conteúdo.
- Sem dependências de outros tasks — pode ser feito em paralelo com qualquer outro.

- [ ] **Step 1: Implement**

Create `frontend/src/lib/components/Modal.svelte`:

```svelte
<script>
  export let aberto = false;
  export let onClose = () => {};

  function fecharTecla(e) {
    if (aberto && e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={fecharTecla} />

{#if aberto}
  <div class="overlay" on:click|self={onClose}>
    <div class="caixa">
      <button class="fechar" on:click={onClose} aria-label="Fechar">✕</button>
      <slot />
    </div>
  </div>
{/if}

<style>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.caixa {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  max-width: 90vw;
  max-height: 85vh;
  overflow: auto;
  position: relative;
  min-width: 320px;
}
.fechar {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 16px;
  cursor: pointer;
}
.fechar:hover { color: var(--text); }
</style>
```

- [ ] **Step 2: Verificação manual isolada**

Criar temporariamente em `frontend/src/routes/+page.svelte` (ou qualquer página logada) um teste manual:

```svelte
<script>
  import Modal from '$lib/components/Modal.svelte';
  let aberto = false;
</script>

<button on:click={() => aberto = true}>abrir modal teste</button>
<Modal {aberto} onClose={() => aberto = false}>
  <p>Conteúdo de teste</p>
</Modal>
```

`docker restart datahub_frontend`, abrir `http://localhost:3000/`, clicar no botão — confirmar que o modal abre centralizado, fecha no X, no ESC e ao clicar fora da caixa. **Reverter essa alteração temporária** em `+page.svelte` antes de prosseguir (não faz parte do código final).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/Modal.svelte
git commit -m "feat: add reusable Modal component"
```

---

## Task 7: Frontend — `GrupoLinha.svelte` + `DynamicTable.svelte` (novos)

**Files:**
- Create: `frontend/src/lib/components/GrupoLinha.svelte`
- Create: `frontend/src/lib/components/DynamicTable.svelte`

**Interfaces:**
- Consumes: `Modal.svelte` (Task 6), `api.executarQuery` (já existe), `DataTable`/`KPICard`/`ChartPanel`/`MapPanel` (já existem).
- Produces: componente `DynamicTable` com props `colunas`, `dados`, `agrupamentos: string[]`, `agregacoes: [{coluna,funcao,label}]`, `subquery: {slug,tipo,parametros:[{coluna_origem,parametro_destino}]} | null`, `titulo`.
- Sem testes automatizados — verificação manual no Task 9 (integrado ao painel real).

- [ ] **Step 1: Implement — `GrupoLinha.svelte`**

Create `frontend/src/lib/components/GrupoLinha.svelte`:

```svelte
<script>
  export let no;              // { folha: true, linhas } | { folha: false, grupos: [{valor, agregados, filho}] }
  export let colunasDetalhe;  // [{key, label}]
  export let mostrarAcoes;
  export let onAcionar;
  export let nivel = 0;
</script>

{#if no.folha}
  {#each no.linhas as row}
    <tr>
      {#each colunasDetalhe as col, i}
        <td style={i === 0 ? `padding-left:${16 + nivel * 16}px` : ''}>{row[col.key] ?? '—'}</td>
      {/each}
      {#if mostrarAcoes}
        <td><button class="btn-ghost btn-sm" on:click={() => onAcionar(row)}>Ações</button></td>
      {/if}
    </tr>
  {/each}
{:else}
  {#each no.grupos as grupo}
    <tr class="linha-grupo">
      <td style="padding-left:{nivel * 16}px" colspan={Math.max(1, colunasDetalhe.length - grupo.agregados.length)}>
        {grupo.valor}
      </td>
      {#each grupo.agregados as ag}
        <td class="agregado">{ag.label ?? ag.coluna}: {ag.valor}</td>
      {/each}
      {#if mostrarAcoes}<td></td>{/if}
    </tr>
    <svelte:self
      no={grupo.filho}
      {colunasDetalhe}
      {mostrarAcoes}
      {onAcionar}
      nivel={nivel + 1}
    />
  {/each}
{/if}

<style>
.linha-grupo { background: var(--surface2); font-weight: 600; }
.agregado { text-align: right; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
```

- [ ] **Step 2: Implement — `DynamicTable.svelte`**

Create `frontend/src/lib/components/DynamicTable.svelte`:

```svelte
<script>
  import GrupoLinha from './GrupoLinha.svelte';
  import Modal from './Modal.svelte';
  import DataTable from './DataTable.svelte';
  import KPICard from './KPICard.svelte';
  import ChartPanel from './ChartPanel.svelte';
  import MapPanel from './MapPanel.svelte';
  import { api } from '$lib/api.js';

  export let colunas = [];
  export let dados = [];
  export let agrupamentos = [];
  export let agregacoes = [];
  export let subquery = null;
  export let titulo = 'dados';

  const FUNCOES = {
    soma:     vals => vals.reduce((a, b) => a + b, 0),
    contagem: vals => vals.length,
    media:    vals => vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
    minimo:   vals => vals.length ? Math.min(...vals) : 0,
    maximo:   vals => vals.length ? Math.max(...vals) : 0,
  };

  function calcularAgregacoes(linhas) {
    return agregacoes.map(ag => {
      const valores = linhas.map(r => Number(r[ag.coluna])).filter(v => !Number.isNaN(v));
      return { coluna: ag.coluna, label: ag.label, valor: (FUNCOES[ag.funcao] ?? FUNCOES.soma)(valores) };
    });
  }

  function construirArvore(linhas, nivel) {
    if (nivel >= agrupamentos.length) return { folha: true, linhas };
    const coluna = agrupamentos[nivel];
    const grupos = new Map();
    for (const linha of linhas) {
      const chave = linha[coluna];
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(linha);
    }
    return {
      folha: false,
      grupos: [...grupos.entries()].map(([valor, linhasGrupo]) => ({
        valor,
        agregados: calcularAgregacoes(linhasGrupo),
        filho: construirArvore(linhasGrupo, nivel + 1),
      })),
    };
  }

  $: colunasDetalhe = (colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
  ).filter(c => !agrupamentos.includes(c.key));

  $: arvore = construirArvore(dados, 0);
  $: mostrarAcoes = !!subquery;

  let modalAberto     = false;
  let modalCarregando = false;
  let modalErro       = null;
  let modalDados      = null;

  async function acionar(row) {
    if (!subquery) return;
    modalAberto     = true;
    modalCarregando = true;
    modalErro       = null;
    modalDados      = null;
    try {
      const params = Object.fromEntries(
        subquery.parametros.map(m => [m.parametro_destino, row[m.coluna_origem]])
      );
      const res = await api.executarQuery(subquery.slug, params);
      modalDados = res.data;
    } catch (e) {
      modalErro = e.message;
    } finally {
      modalCarregando = false;
    }
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunasDetalhe as col}<th>{col.label ?? col.key}</th>{/each}
        {#if mostrarAcoes}<th>Ações</th>{/if}
      </tr>
    </thead>
    <tbody>
      <GrupoLinha no={arvore} {colunasDetalhe} {mostrarAcoes} onAcionar={acionar} nivel={0} />
    </tbody>
  </table>
</div>

<Modal aberto={modalAberto} onClose={() => modalAberto = false}>
  {#if modalCarregando}
    <p>Carregando...</p>
  {:else if modalErro}
    <p class="error">{modalErro}</p>
  {:else if subquery?.tipo === 'kpi'}
    <KPICard dados={modalDados?.[0]} />
  {:else if subquery?.tipo?.startsWith('chart_')}
    <ChartPanel tipo={subquery.tipo} dados={modalDados ?? []} />
  {:else if subquery?.tipo === 'map'}
    <MapPanel pontos={modalDados ?? []} />
  {:else}
    <DataTable dados={modalDados ?? []} titulo={titulo} />
  {/if}
</Modal>

<style>
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.error { color: var(--danger, #f85149); }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/GrupoLinha.svelte frontend/src/lib/components/DynamicTable.svelte
git commit -m "feat: add DynamicTable component with grouped rendering and subquery drill-down"
```

---

## Task 8: Frontend — telas de configuração de query (`nova` e `[id]`)

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`

**Interfaces:**
- Consumes: `api.listarQueries`, `api.parametrosQuery`, `api.agrupamentosQuery/salvarAgrupamentosQuery`, `api.agregacoesQuery/salvarAgregacoesQuery`, `api.subqueryParametrosQuery/salvarSubqueryParametrosQuery` (Task 5).
- Sem testes automatizados — verificado manualmente no Task 9.

- [ ] **Step 1: `nova/+page.svelte` — estado e tipos**

`tipos` (linha 30-34): adicionar `'table_dynamic'`:

```js
  const tipos = [
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map', 'table_dynamic'
  ];
```

`form` (linha 7-19): adicionar após `meta_cor_fora: '#f85149'`:

```js
    subquery_id: null,
```

Novas variáveis locais, após `let erro = null;` (linha 28):

```js
  let agrupamentos       = []; // [{coluna, ordem}]
  let agregacoes         = []; // [{coluna, funcao, label, ordem}]
  let queriesDisponiveis = [];
  let subqueryParams     = []; // parâmetros da query_parametros da subconsulta escolhida
  let mapeamentoSubquery = []; // [{coluna_origem, parametro_destino}] — mesmo tamanho de subqueryParams
```

No `onMount` (linha 36-48), carregar as queries disponíveis junto com empresas/variáveis:

```js
  onMount(async () => {
    try {
      const [emps, vars, qs] = await Promise.all([
        api.listarEmpresas(),
        api.listarVariaveis(),
        api.listarQueries(),
      ]);
      empresas  = emps;
      variaveis = vars.filter(v => v.ativo);
      queriesDisponiveis = qs;
      if (emps.length > 0) testarEmpresaId = emps[0].id;
    } catch (e) {
      console.error('Erro ao carregar dados:', e);
    }
  });
```

Funções novas, logo após `removerParam` (linha 84-87):

```js
  function adicionarAgrupamento() {
    agrupamentos = [...agrupamentos, { coluna: '', ordem: agrupamentos.length }];
  }
  function removerAgrupamento(i) {
    agrupamentos = agrupamentos.filter((_, idx) => idx !== i).map((a, idx) => ({ ...a, ordem: idx }));
  }
  function moverAgrupamento(i, direcao) {
    const j = i + direcao;
    if (j < 0 || j >= agrupamentos.length) return;
    const copia = [...agrupamentos];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    agrupamentos = copia.map((a, idx) => ({ ...a, ordem: idx }));
  }

  function adicionarAgregacao() {
    agregacoes = [...agregacoes, { coluna: '', funcao: 'soma', label: '', ordem: agregacoes.length }];
  }
  function removerAgregacao(i) {
    agregacoes = agregacoes.filter((_, idx) => idx !== i).map((a, idx) => ({ ...a, ordem: idx }));
  }

  async function onSubqueryChange() {
    mapeamentoSubquery = [];
    if (!form.subquery_id) {
      subqueryParams = [];
      return;
    }
    subqueryParams = await api.parametrosQuery(form.subquery_id);
    mapeamentoSubquery = subqueryParams.map((p, idx) => ({ coluna_origem: '', parametro_destino: p.nome, ordem: idx }));
  }
```

- [ ] **Step 2: `nova/+page.svelte` — bloco de template**

Adicionar logo após o bloco `{#if form.tipo === 'table'}` de Coloração por Meta (linha 236-294), antes do bloco de gráficos:

```svelte
    {#if form.tipo === 'table_dynamic'}
      <div class="section-block">
        <div class="section-header">
          <span class="section-title">Agrupamento</span>
          <button class="btn-ghost btn-sm" on:click={adicionarAgrupamento}>+ Nível</button>
        </div>
        {#if agrupamentos.length === 0}
          <p class="hint-block">Sem agrupamento — teste a query e adicione ao menos 1 nível.</p>
        {/if}
        {#each agrupamentos as ag, i}
          <div class="agrup-row">
            <span class="pos-badge">Nível {i + 1}</span>
            <select bind:value={ag.coluna}>
              <option value="">— selecione —</option>
              {#each resultadoTeste?.colunas ?? (ag.coluna ? [ag.coluna] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
            <button class="btn-ghost btn-sm" on:click={() => moverAgrupamento(i, -1)} disabled={i === 0}>↑</button>
            <button class="btn-ghost btn-sm" on:click={() => moverAgrupamento(i, 1)} disabled={i === agrupamentos.length - 1}>↓</button>
            <button class="btn-ghost btn-sm danger" on:click={() => removerAgrupamento(i)}>✕</button>
          </div>
        {/each}
      </div>

      <div class="section-block">
        <div class="section-header">
          <span class="section-title">Agregações</span>
          <button class="btn-ghost btn-sm" on:click={adicionarAgregacao}>+ Agregação</button>
        </div>
        {#each agregacoes as ag, i}
          <div class="agreg-row">
            <select bind:value={ag.coluna}>
              <option value="">— coluna —</option>
              {#each resultadoTeste?.colunas ?? (ag.coluna ? [ag.coluna] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
            <select bind:value={ag.funcao}>
              <option value="soma">Soma</option>
              <option value="contagem">Contagem</option>
              <option value="media">Média</option>
              <option value="minimo">Mínimo</option>
              <option value="maximo">Máximo</option>
            </select>
            <input bind:value={ag.label} placeholder="Rótulo (opcional)" />
            <button class="btn-ghost btn-sm danger" on:click={() => removerAgregacao(i)}>✕</button>
          </div>
        {/each}
      </div>

      <div class="section-block">
        <span class="section-title">Subconsulta (drill-down)</span>
        <label class="lbl">
          Query chamada ao clicar em "Ações"
          <select bind:value={form.subquery_id} on:change={onSubqueryChange}>
            <option value={null}>— nenhuma —</option>
            {#each queriesDisponiveis.filter(q => q.slug !== form.slug) as q}
              <option value={q.id}>{q.nome} ({q.tipo})</option>
            {/each}
          </select>
        </label>
        {#if subqueryParams.length > 0}
          <p class="hint-block">Para cada parâmetro da subconsulta, escolha de qual coluna desta query o valor vem:</p>
          {#each subqueryParams as p, i}
            <div class="agrup-row">
              <span class="pos-badge">{p.nome}</span>
              <select bind:value={mapeamentoSubquery[i].coluna_origem}>
                <option value="">— coluna —</option>
                {#each resultadoTeste?.colunas ?? [] as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </div>
          {/each}
        {:else if form.subquery_id}
          <p class="hint-block">Essa subconsulta não tem parâmetros cadastrados.</p>
        {/if}
      </div>
    {/if}
```

- [ ] **Step 3: `nova/+page.svelte` — salvar**

`salvar()` (linha 105-131): depois de `await api.salvarParametrosQuery(...)`, adicionar:

```js
      if (form.tipo === 'table_dynamic') {
        await api.salvarAgrupamentosQuery(q.id, agrupamentos.filter(a => a.coluna));
        await api.salvarAgregacoesQuery(q.id, agregacoes.filter(a => a.coluna));
        if (form.subquery_id) {
          await api.salvarSubqueryParametrosQuery(
            q.id,
            mapeamentoSubquery.filter(m => m.coluna_origem)
          );
        }
      }
```

- [ ] **Step 4: `nova/+page.svelte` — estilos novos**

No `<style>` (final do arquivo), adicionar:

```css
.agrup-row { display: grid; grid-template-columns: 90px 1fr 32px 32px 32px; gap: 6px; align-items: center; }
.agreg-row { display: grid; grid-template-columns: 1fr 1fr 1fr 32px; gap: 6px; align-items: center; }
```

- [ ] **Step 5: `[id]/+page.svelte` — mesmo conjunto de mudanças, com carga inicial**

Repetir os Steps 1-4 em `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`, com estas diferenças:

`tipos` (linha 34-38): mesma adição de `'table_dynamic'`.

`form` (linha 10-22): mesma adição de `subquery_id: null,`.

Variáveis locais: mesmas do Step 1, adicionadas após `let erro = null;` (linha 32).

`onMount` (linha 40-84): carregar também `agrupamentosQuery`, `agregacoesQuery`, `subqueryParametrosQuery` e `listarQueries`, e popular `form.subquery_id`:

```js
  onMount(async () => {
    try {
      const [q, emps, prms, vars, qs] = await Promise.all([
        api.buscarQuery(id),
        api.listarEmpresas(),
        api.parametrosQuery(id),
        api.listarVariaveis(),
        api.listarQueries(),
      ]);
      empresas  = emps;
      variaveis = vars.filter(v => v.ativo);
      queriesDisponiveis = qs;
      if (emps.length > 0) testarEmpresaId = emps[0].id;
      form = {
        slug:          q.slug,
        nome:          q.nome,
        descricao:     q.descricao || '',
        sql_texto:     q.sql_texto,
        tipo:          q.tipo,
        empresa_id:    q.empresa_id,
        cache_ttl:     q.cache_ttl,
        ativo:         q.ativo,
        kpi_cor_fonte: q.kpi_cor_fonte || '#e6edf3',
        kpi_cor_fundo: q.kpi_cor_fundo || '#161b22',
        mapa_camada:   q.mapa_camada || 'padrao',
        chart_fonte_tamanho:   q.chart_fonte_tamanho ?? 12,
        chart_truncar_label:   q.chart_truncar_label ?? false,
        chart_truncar_tamanho: q.chart_truncar_tamanho ?? 15,
        chart_mostrar_valor:   q.chart_mostrar_valor ?? false,
        chart_valor_label:     q.chart_valor_label || '',
        impressao_habilitada: q.impressao_habilitada ?? false,
        impressao_caminho:    q.impressao_caminho || '',
        impressao_coluna:     q.impressao_coluna || '',
        meta_habilitada:    q.meta_habilitada ?? false,
        meta_coluna_valor:  q.meta_coluna_valor || '',
        meta_coluna_inicio: q.meta_coluna_inicio || '',
        meta_coluna_fim:    q.meta_coluna_fim || '',
        meta_cor_dentro:    q.meta_cor_dentro || '#3fb950',
        meta_cor_fora:      q.meta_cor_fora || '#f85149',
        subquery_id:        q.subquery_id ?? null,
      };
      params = prms.map(p => ({ ...p, _testar_valor: '' }));

      if (q.tipo === 'table_dynamic') {
        agrupamentos = await api.agrupamentosQuery(id);
        agregacoes   = await api.agregacoesQuery(id);
        if (q.subquery_id) {
          subqueryParams = await api.parametrosQuery(q.subquery_id);
          const salvos = await api.subqueryParametrosQuery(id);
          mapeamentoSubquery = subqueryParams.map((p, idx) => {
            const existente = salvos.find(s => s.parametro_destino === p.nome);
            return { coluna_origem: existente?.coluna_origem ?? '', parametro_destino: p.nome, ordem: idx };
          });
        }
      }
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });
```

Bloco de template: igual ao Step 2, inserido no mesmo ponto relativo (depois do bloco de Coloração por Meta, linha 299-357, antes do bloco de gráficos), com a indentação de 6 espaços já usada no restante do arquivo (dentro do `{:else}` do `{#if carregando}`).

`salvar()` (linha 139-179): no payload de `atualizarQuery`, adicionar `subquery_id: form.subquery_id,` após `meta_cor_fora`; e, depois de `await api.salvarParametrosQuery(...)`, adicionar o mesmo bloco do Step 3:

```js
      if (form.tipo === 'table_dynamic') {
        await api.salvarAgrupamentosQuery(id, agrupamentos.filter(a => a.coluna));
        await api.salvarAgregacoesQuery(id, agregacoes.filter(a => a.coluna));
        if (form.subquery_id) {
          await api.salvarSubqueryParametrosQuery(
            id,
            mapeamentoSubquery.filter(m => m.coluna_origem)
          );
        }
      }
```

Mesmos estilos novos do Step 4.

- [ ] **Step 6: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 7: Commit**

```bash
git add "frontend/src/routes/configuracoes/queries/nova/+page.svelte" "frontend/src/routes/configuracoes/queries/[id]/+page.svelte"
git commit -m "feat: add table_dynamic config UI (grouping, aggregation, subquery mapping)"
```

---

## Task 9: Frontend — encaixe no painel + verificação manual completa

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `DynamicTable.svelte` (Task 7), campos `agrupamentos`/`agregacoes`/`subquery` anexados pelo backend (Task 4).

- [ ] **Step 1: Import e branch de renderização**

Adicionar import junto dos demais componentes (linha 5-9):

```js
  import DynamicTable   from '$lib/components/DynamicTable.svelte';
```

Novo branch no `{#if ind.query_tipo === ...}` (depois do bloco `{:else if ind.query_tipo === 'table'}`, linha ~243-260, antes de `{:else if ind.query_tipo === 'map'}`):

```svelte
            {:else if ind.query_tipo === 'table_dynamic'}
              <DynamicTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                agrupamentos={ind.agrupamentos ?? []}
                agregacoes={ind.agregacoes ?? []}
                subquery={ind.subquery}
              />
```

- [ ] **Step 2: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Verificação manual completa**

1. Em Configurações → Queries → nova, tipo `table_dynamic`, SQL:
   ```sql
   SELECT 'Fazenda Manga' AS fazenda, 'Equipamento 1' AS equipamento, 3 AS qtd
   UNION ALL SELECT 'Fazenda Manga', 'Equipamento 2', 5
   UNION ALL SELECT 'Fazenda Santa Água', 'Equipamento 1', 2
   ```
   empresa `alpha`, clicar "Testar" — confirmar que "Agrupamento"/"Agregações" mostram `fazenda`, `equipamento`, `qtd` como opções.
2. Adicionar 1 nível de agrupamento (`fazenda`), 1 agregação (`qtd`, soma, label "Total"). Salvar.
3. Criar um painel, adicionar essa query como indicador, abrir o painel.
4. Confirmar: 2 linhas de grupo (`Fazenda Manga` com Total: 8, `Fazenda Santa Água` com Total: 2), cada uma com as linhas de detalhe (`equipamento`, `qtd`) embaixo, sem coluna "Ações" (sem subconsulta configurada ainda).
5. Criar uma segunda query tipo `kpi` (SQL `SELECT $1::int AS valor` com 1 parâmetro manual `qtd_recebida`). Editar a query `table_dynamic`, escolher essa query como "Subconsulta", mapear `qtd` → `qtd_recebida`. Salvar.
6. Recarregar o painel — confirmar que a coluna "Ações" aparece nas linhas de detalhe. Clicar — confirmar que o dialog abre, mostra "Carregando...", depois o KPI com o valor da linha clicada.
7. Editar a subconsulta pra ter SQL inválido (ex: `SELECT * FROM tabela_que_nao_existe`) temporariamente, clicar "Ações" de novo — confirmar que o dialog mostra a mensagem de erro em vez de quebrar a tela. Reverter o SQL da subconsulta depois do teste.
8. Testar com 2 níveis de agrupamento (adicionar `equipamento` como 2º nível) — confirmar indentação e que a agregação aparece em ambos os níveis corretamente.
9. Confirmar que `table`, `kpi`, `chart_*` e `map` (outros tipos de query) continuam funcionando sem nenhuma regressão visual.

- [ ] **Step 4: Reverter dados de teste**

Apagar as queries e o painel de teste criados nos passos 3.1, 3.3 e 3.5 (Configurações → Queries / Painéis).

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: render table_dynamic indicators in painel view"
```
