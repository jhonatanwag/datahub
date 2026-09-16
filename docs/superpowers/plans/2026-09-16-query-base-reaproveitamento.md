# Query Base — Reaproveitamento de SQL entre Indicadores Irmãos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduzir `queries.query_base_id` pra que uma query "derivada" possa reaproveitar o `FROM`/`JOIN`/`WHERE` de outra query "base" via CTE (`WITH base AS (...) <sql da derivada>`), eliminando a duplicação de bloco de JOIN entre queries irmãs do mesmo domínio — e migrar o grupo "Pendência" (30 queries reais em dev) como piloto.

**Architecture:** Campo novo em `queries` (FK simples, 1 nível só, sem tabela filha). `resolver_query`/`testar_query` compõem a CTE em tempo de execução quando `query_base_id` está setado, usando os `query_parametros` da base (a derivada normalmente não tem parâmetro próprio). `routes/queries.py` valida/persiste o vínculo; `services/portabilidade.py` trata a base como dependência transitiva (mesmo padrão já usado pra `subquery_id`); o frontend ganha um seletor "Query base" nas telas de nova/editar query.

**Tech Stack:** FastAPI + asyncpg (backend), SvelteKit sem TypeScript (frontend), PostgreSQL (`datahub_meta` em dev via `docker exec datahub_postgres`), pytest (`docker exec datahub_backend python -m pytest`).

**Spec:** `docs/superpowers/specs/2026-09-16-query-base-reaproveitamento-design.md`

## Global Constraints

- Só 1 nível de base — uma query que já é derivada (`query_base_id IS NOT NULL`) não pode ser escolhida como base de outra.
- Parâmetros posicionais (`$1..$N`) da derivada pertencem à base; a derivada só declara `query_parametros` próprios quando precisa de um filtro extra, numerado **depois** dos da base.
- Nenhuma mudança no contrato de retorno por `tipo`, em `renderizar_painel`, nem nos componentes de frontend que consomem `ind.dados` — só a origem do dado bruto passa a ser compartilhada.
- Cache continua por slug da própria derivada (Fase 2, fora de escopo aqui) — mas editar `sql_texto`/`ativo`/`slug` de uma query que é base de outras precisa invalidar o cache de todas as derivadas.
- Slugs das 30 queries do grupo Pendência **não mudam** na migração piloto — `painel_indicadores.query_slug` continua intacto nos 3 painéis (`pen_pendencias_equip`, `pen_pendencias_sede`, `pen_pendencias_lavoura`).
- Toda alteração de schema em dev precisa ser refletida em `scripts/init-db.sql`, `scripts/init-meta-prod.sql` e documentada em `README.md` ("Deltas de schema pendentes") — produção não recebe deploy automático.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `scripts/init-db.sql`, `scripts/init-meta-prod.sql` | Coluna `query_base_id` + índice no schema de referência |
| `README.md` | Registro do delta de schema pendente em produção |
| `backend/services/query_runner.py` | Composição da CTE em `resolver_query`; novo helper `invalidar_cache_derivadas` |
| `backend/routes/queries.py` | Campo no `QueryInput`/`QueryUpdate`; validação `_validar_query_base`; wiring em `criar_query`/`atualizar_query`/`testar_query`/`duplicar_query` |
| `backend/services/portabilidade.py` | `base_query_slug` no bundle; fecho transitivo; diff; resolução em 2 passos no import |
| `backend/tests/test_queries_base.py` (novo) | Cobertura de `query_base_id`: criação, validação de 1 nível, cache em cascata, duplicação, teste com base |
| `backend/tests/test_portabilidade_paineis.py` | +2 testes: export traz a base no bundle; import resolve `base_query_slug` |
| `frontend/src/routes/configuracoes/queries/nova/+page.svelte` | Seletor "Query base" + fluxo de teste com parâmetros da base |
| `frontend/src/routes/configuracoes/queries/[id]/+page.svelte` | Mesmo seletor, espelhado no fluxo de edição |
| Banco `datahub_meta` (dev, via `docker exec datahub_postgres psql`) | Migração piloto: 3 queries base + 30 derivadas reescritas no grupo Pendência |

---

### Task 1: Schema — coluna `query_base_id`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md` (seção "Deltas de schema pendentes")
- Banco de dev: `datahub_meta` via `docker exec datahub_postgres psql -U postgres -d datahub_meta`

**Interfaces:**
- Produces: coluna `queries.query_base_id INTEGER REFERENCES queries(id) ON DELETE SET NULL` + índice `idx_queries_base` — usada por todas as tasks seguintes.

- [x] **Step 1: Aplicar no banco de dev**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
ALTER TABLE queries ADD COLUMN query_base_id INTEGER REFERENCES queries(id) ON DELETE SET NULL;
CREATE INDEX idx_queries_base ON queries(query_base_id);
"
```

- [x] **Step 2: Verificar que a coluna e o índice existem**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\d queries" | grep -E "query_base_id|idx_queries_base"
```

Expected: a linha `query_base_id | integer` aparece na lista de colunas, e `idx_queries_base` aparece em Indexes.

- [x] **Step 3: Refletir no schema de referência local**

Em `scripts/init-db.sql`, localizar o bloco `CREATE TABLE queries (...)` e a linha que hoje cria `subquery_id` (mesma coluna que serviu de precedente pra esse padrão). Adicionar logo depois dela:

```sql
    query_base_id INTEGER REFERENCES queries(id) ON DELETE SET NULL,
```

E depois do bloco de `CREATE INDEX` de `queries`, adicionar:

```sql
CREATE INDEX idx_queries_base ON queries(query_base_id);
```

- [x] **Step 4: Refletir no schema de produção**

Repetir exatamente o mesmo par de edições (coluna + índice) em `scripts/init-meta-prod.sql`, no mesmo formato.

- [x] **Step 5: Documentar a pendência de produção**

Em `README.md`, seção "Deltas de schema pendentes" (mesmo bloco onde outras colunas novas já foram documentadas, ex. `tema`), adicionar:

```sql
-- Reaproveitamento de SQL entre queries irmãs (query base / CTE)
ALTER TABLE queries ADD COLUMN query_base_id INTEGER REFERENCES queries(id) ON DELETE SET NULL;
CREATE INDEX idx_queries_base ON queries(query_base_id);
```

- [x] **Step 6: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md
git commit -m "feat: coluna query_base_id em queries (reaproveitamento de SQL entre irmãs)"
```

---

### Task 2: Backend — composição da CTE em `resolver_query`

**Files:**
- Modify: `backend/services/query_runner.py:76-149` (`resolver_query`), depois de `invalidar_cache_query` (linha 152-161)
- Test: `backend/tests/test_queries_base.py` (novo)

**Interfaces:**
- Consumes: nada de tasks anteriores (só a coluna do schema).
- Produces: `resolver_query` passa a aceitar queries com `query_base_id` preenchido; novo `invalidar_cache_derivadas(query_id: int) -> None` em `query_runner.py`, usado pela Task 3.

- [x] **Step 1: Escrever o teste que falha**

Criar `backend/tests/test_queries_base.py`:

```python
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
```

- [x] **Step 2: Rodar e confirmar que falha**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_base.py::test_derivada_executa_via_cte_da_base -v
```

Expected: FAIL — `criar_query` aceita `query_base_id` no payload (Pydantic ignora campo desconhecido silenciosamente hoje... na verdade não, `QueryInput` ainda não tem o campo, então o valor é descartado) e a query derivada é gravada com `sql_texto` que referencia `base`, uma tabela inexistente → `executar` retorna 500 (`relation "base" does not exist`), não 200.

- [x] **Step 3: Implementar a composição da CTE**

Em `backend/services/query_runner.py`, dentro de `resolver_query` (linha 98, logo após `query = dict(rows[0])`), inserir:

```python
    sql = query["sql_texto"]
    query_params_id = query["id"]

    if query.get("query_base_id"):
        base_rows = await query_meta(
            "SELECT * FROM queries WHERE id = $1 AND ativo = true", query["query_base_id"]
        )
        if not base_rows:
            raise ValueError(f"Query base de '{slug}' não encontrada ou inativa")
        base = dict(base_rows[0])
        sql = f"WITH base AS ({base['sql_texto']}) {query['sql_texto']}"
        query_params_id = base["id"]
```

Substituir a linha 108 (`sql = query["sql_texto"]`, agora redundante) — remover essa linha original, já coberta acima.

Substituir a chamada de `param_rows` (linha 110-116 atual) pra usar `query_params_id` em vez de `query["id"]`:

```python
    param_rows = await query_meta("""
        SELECT qp.*, v.slug AS variavel_slug
        FROM query_parametros qp
        LEFT JOIN variaveis v ON v.id = qp.variavel_id
        WHERE qp.query_id = $1
        ORDER BY qp.id
    """, query_params_id)

    if query.get("query_base_id"):
        param_rows += await query_meta("""
            SELECT qp.*, v.slug AS variavel_slug
            FROM query_parametros qp
            LEFT JOIN variaveis v ON v.id = qp.variavel_id
            WHERE qp.query_id = $1
            ORDER BY qp.id
        """, query["id"])
```

O resto da função (loop de `valores`, `_cast`, `query_company`, cache) não muda.

- [x] **Step 4: Rodar e confirmar que passa**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_base.py::test_derivada_executa_via_cte_da_base -v
```

Ainda deve falhar nesse ponto — `criar_query` ainda não persiste `query_base_id` (isso é a Task 3). Confirmar que o erro mudou: agora é 200 mas com dados vazios/errados, ou ainda erro de "relation base does not exist" se o campo continuar sendo descartado no `POST`. **Esperado neste passo: ainda falha, mas por causa da Task 3, não da Task 2** — documentar isso no commit da Task 2 e seguir; o teste só vai passar de verdade ao final da Task 3.

- [x] **Step 5: Adicionar `invalidar_cache_derivadas`**

Em `backend/services/query_runner.py`, logo depois de `invalidar_cache_query` (linha 152-161):

```python
async def invalidar_cache_derivadas(query_id: int):
    """Se `query_id` é base de outras queries, o SQL delas depende do SQL
    dela — invalida o cache de cada derivada (elas não sabem, pelo próprio
    slug, que dependem de uma base que mudou)."""
    derivadas = await query_meta("SELECT slug FROM queries WHERE query_base_id = $1", query_id)
    for d in derivadas:
        await invalidar_cache_query(d["slug"])
```

- [x] **Step 6: Commit**

```bash
git add backend/services/query_runner.py backend/tests/test_queries_base.py
git commit -m "feat: resolver_query compõe CTE quando query_base_id está setado"
```

---

### Task 3: Backend — `routes/queries.py` (criar/editar/testar/duplicar)

**Files:**
- Modify: `backend/routes/queries.py:6` (import), `:12-48` (`QueryInput`), `:51-84` (`QueryUpdate`), `:187-216` (`testar_query`), `:399-453` (`criar_query`), `:456-539` (`atualizar_query`), `:542-606` (`duplicar_query`)
- Test: `backend/tests/test_queries_base.py` (continuação)

**Interfaces:**
- Consumes: `invalidar_cache_derivadas` (Task 2, `services/query_runner.py`).
- Produces: `POST/PATCH /api/queries` aceitam e validam `query_base_id`; `POST /api/queries/testar` compõe a CTE; `POST /api/queries/{id}/duplicar` preserva o vínculo.

- [x] **Step 1: Escrever os testes que faltam (continuação de `test_queries_base.py`)**

```python
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
```

- [x] **Step 2: Rodar e confirmar que falham**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_base.py -v
```

Expected: todos os testes novos falham (400 esperado vira 200, `query_base_id` não persiste, `testar` não compõe CTE).

- [x] **Step 3: Adicionar o campo aos modelos**

Em `backend/routes/queries.py:47` (logo após `chart_filtro_coluna: Optional[str] = None` em `QueryInput`), adicionar:

```python
    query_base_id: Optional[int] = None
```

Fazer o mesmo em `QueryUpdate`, logo após a linha equivalente (linha 83):

```python
    query_base_id: Optional[int] = None
```

- [x] **Step 4: Importar o novo helper**

Em `backend/routes/queries.py:6`, trocar:

```python
from services.query_runner import resolver_query, invalidar_cache_query, validar_sql, _cast
```

por:

```python
from services.query_runner import resolver_query, invalidar_cache_query, invalidar_cache_derivadas, validar_sql, _cast
```

- [x] **Step 5: Criar o helper de validação**

Em `backend/routes/queries.py`, logo depois de `_com_kpi_imagem_url` (depois da linha 139), adicionar:

```python
async def _validar_query_base(query_base_id: Optional[int], excluir_id: Optional[int] = None):
    if query_base_id is None:
        return
    if query_base_id == excluir_id:
        raise HTTPException(status_code=400, detail="Uma query não pode ser base dela mesma.")
    rows = await query_meta("SELECT id, query_base_id, ativo FROM queries WHERE id = $1", query_base_id)
    if not rows or not rows[0]["ativo"]:
        raise HTTPException(status_code=400, detail=f"Query base #{query_base_id} não encontrada ou inativa.")
    if rows[0]["query_base_id"] is not None:
        raise HTTPException(
            status_code=400,
            detail="Não é permitido encadear: a query escolhida como base já é derivada de outra.",
        )
```

- [x] **Step 6: Validar e incluir no `criar_query`**

Em `backend/routes/queries.py:418` (logo após `validar_sql(body.sql_texto)`, antes de `grupo_id = await resolver_grupo_id(...)`), adicionar:

```python
        await _validar_query_base(body.query_base_id)
```

No `INSERT` de `criar_query` (linhas 421-446), adicionar `query_base_id` à lista de colunas e ao final do `VALUES` — a lista de colunas (linha 422-431) passa a terminar com:

```python
                chart_filtro_coluna, grupo_id, kpi_valor_primeiro, chart_rotulo_eixo, chart_rotulo_valor,
                query_base_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35)
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
            body.meta_cor_dentro, body.meta_cor_fora, body.subquery_id,
            body.pdf_orientacao, body.kpi_imagem_habilitada, body.kpi_imagem_posicao,
            body.chart_filtro_coluna, grupo_id, body.kpi_valor_primeiro, body.chart_rotulo_eixo,
            body.chart_rotulo_valor, body.query_base_id)
```

(Contagem de `$N` sobe de 34 pra 35; o resto do `INSERT` fica igual.)

- [x] **Step 7: Validar e incluir no `atualizar_query`**

Em `backend/routes/queries.py:480` (dentro de `ALLOWED_COLS`), adicionar `'query_base_id'` ao conjunto:

```python
            'kpi_valor_primeiro', 'chart_filtro_coluna', 'chart_rotulo_eixo', 'chart_rotulo_valor',
            'query_base_id'
```

Depois do bloco de validações existentes (depois da linha 512, antes de `if "sql_texto" in updates:` na linha 514), adicionar:

```python
        if "query_base_id" in updates:
            await _validar_query_base(updates["query_base_id"], excluir_id=query_id)
```

Trocar a condição de invalidação de cache (linha 530-531):

```python
        if "sql_texto" in updates or "slug" in updates:
            await invalidar_cache_query(atual["slug"])
```

por:

```python
        if "sql_texto" in updates or "slug" in updates or "ativo" in updates:
            await invalidar_cache_query(atual["slug"])
            await invalidar_cache_derivadas(query_id)
```

- [x] **Step 8: Compor a CTE em `testar_query`**

Em `backend/routes/queries.py:187-216`, depois de `validar_sql(body.sql_texto)` (linha 190), adicionar:

```python
        sql_para_rodar = body.sql_texto
        if body.query_base_id:
            base_rows = await query_meta(
                "SELECT sql_texto FROM queries WHERE id = $1 AND ativo = true", body.query_base_id
            )
            if not base_rows:
                return {"ok": False, "erro": f"Query base #{body.query_base_id} não encontrada ou inativa"}
            sql_para_rodar = f"WITH base AS ({base_rows[0]['sql_texto']}) {body.sql_texto}"
```

E trocar a linha 205 de:

```python
        resultado = await query_company(company_slug, body.sql_texto, *valores)
```

para:

```python
        resultado = await query_company(company_slug, sql_para_rodar, *valores)
```

- [x] **Step 9: Incluir na duplicação**

Em `backend/routes/queries.py:561-585` (`duplicar_query`), adicionar `query_base_id` às duas listas de colunas do `INSERT ... SELECT` (linhas 570-571 e 581-582 — as duas ocorrências de `chart_rotulo_eixo, chart_rotulo_valor`):

```python
                chart_filtro_coluna, kpi_imagem, kpi_imagem_mime, grupo_id, kpi_valor_primeiro,
                chart_rotulo_eixo, chart_rotulo_valor, query_base_id
```

(mesma troca nas duas ocorrências — a lista de colunas do `INSERT INTO queries (...)` e a lista espelhada do `SELECT ...`.)

- [x] **Step 10: Rodar e confirmar que passam**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_base.py -v
```

Expected: todos os testes (Task 2 + Task 3) em PASS.

- [x] **Step 11: Rodar a suíte completa (regressão)**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```

Expected: nenhum teste pré-existente quebrou (`subquery_id`, `table_dynamic`, `portabilidade` etc. continuam passando sem alteração de comportamento).

- [x] **Step 12: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_queries_base.py
git commit -m "feat: query_base_id em criar/editar/testar/duplicar query, com validação de 1 nível e cache em cascata"
```

---

### Task 4: Backend — `services/portabilidade.py` (export/import)

**Files:**
- Modify: `backend/services/portabilidade.py:53-85` (`_serializar_query`), `:119-185` (`montar_bundle_painel`), `:217-220` (`_QUERY_DIFF_KEYS`), `:568-583` (`importar_bundle`, resolução em 2 passos)
- Test: `backend/tests/test_portabilidade_paineis.py` (2 testes novos)

**Interfaces:**
- Consumes: `query_base_id` persistido (Task 3).
- Produces: bundle de export inclui `base_query_slug`; import resolve o vínculo por slug, mesmo padrão de `subquery_slug`.

- [x] **Step 1: Escrever os testes que faltam**

Em `backend/tests/test_portabilidade_paineis.py`, adicionar (usando os helpers `_headers`/`_criar_query`/`_criar_painel` já existentes no topo do arquivo):

```python
def test_exportar_traz_fecho_transitivo_de_query_base(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS grupo, 10 AS valor")
    derivada = _criar_query(client, t, tipo="table", sql_texto="SELECT grupo, valor FROM base", query_base_id=base["id"])
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": derivada["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))
    try:
        r = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t))
        assert r.status_code == 200, r.text
        b = r.json()
        query_slugs = {q["slug"] for q in b["queries"]}
        assert derivada["slug"] in query_slugs
        assert base["slug"] in query_slugs  # fecho transitivo da base
        dq = next(q for q in b["queries"] if q["slug"] == derivada["slug"])
        assert dq["base_query_slug"] == base["slug"]
    finally:
        hard_delete_painel(painel["id"])
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))


def test_importar_resolve_base_query_slug(client, auth_token):
    t = auth_token
    base = _criar_query(client, t, tipo="table", sql_texto="SELECT 1 AS grupo, 10 AS valor")
    derivada = _criar_query(client, t, tipo="table", sql_texto="SELECT grupo, valor FROM base", query_base_id=base["id"])
    painel = _criar_painel(client, t)
    client.put(f"/api/paineis/{painel['id']}/indicadores",
               json=[{"query_slug": derivada["slug"], "linha": 1, "coluna": 1}],
               headers=_headers(t))
    try:
        bundle = client.get(f"/api/paineis/{painel['id']}/exportar", headers=_headers(t)).json()

        # apaga tudo e reimporta do zero — simula levar pra outro ambiente
        client.delete(f"/api/queries/{derivada['id']}", headers=_headers(t))
        client.delete(f"/api/queries/{base['id']}", headers=_headers(t))
        hard_delete_painel(painel["id"])

        r = client.post(
            "/api/portabilidade/paineis/importar",
            json={
                "bundle": bundle,
                "aplicar": {
                    "variaveis": [], "painel": True,
                    "queries": [derivada["slug"], base["slug"]],
                },
            },
            headers=_headers(t),
        )
        assert r.status_code == 200, r.text

        nova_derivada = client.get(f"/api/queries/", headers=_headers(t)).json()
        nova_derivada = next(q for q in nova_derivada if q["slug"] == derivada["slug"])
        nova_base = next(q for q in client.get("/api/queries/", headers=_headers(t)).json() if q["slug"] == base["slug"])
        assert nova_derivada["query_base_id"] == nova_base["id"]
    finally:
        for q in client.get("/api/queries/", headers=_headers(t)).json():
            if q["slug"] in (derivada["slug"], base["slug"]):
                client.delete(f"/api/queries/{q['id']}", headers=_headers(t))
        paineis = client.get("/api/paineis/", headers=_headers(t)).json()
        for p in paineis:
            if p["slug"] == painel["slug"]:
                hard_delete_painel(p["id"])
```

- [x] **Step 2: Rodar e confirmar que falham**

```bash
docker exec datahub_backend python -m pytest tests/test_portabilidade_paineis.py::test_exportar_traz_fecho_transitivo_de_query_base tests/test_portabilidade_paineis.py::test_importar_resolve_base_query_slug -v
```

Expected: FAIL — `base_query_slug` não existe no bundle; `query_base_id` fica `None` depois do import.

- [x] **Step 3: Serializar `base_query_slug`**

Em `backend/services/portabilidade.py:57` (logo após a linha de `subquery_slug`), adicionar:

```python
    out["base_query_slug"] = await _nome_por_id("queries", "slug", row["query_base_id"])
```

- [x] **Step 4: Incluir no fecho transitivo do export**

Em `montar_bundle_painel`, logo depois do bloco de `subquery_id` (linhas 146-149), adicionar:

```python
        if rowq["query_base_id"]:
            base = await query_meta("SELECT slug FROM queries WHERE id = $1", rowq["query_base_id"])
            if base:
                fila.append(base[0]["slug"])
```

- [x] **Step 5: Incluir no diff de conflito**

Em `backend/services/portabilidade.py:217-220`, adicionar `"base_query_slug"` à lista `_QUERY_DIFF_KEYS`:

```python
_QUERY_DIFF_KEYS = QUERY_CAMPOS + [
    "grupo_nome", "empresa_slug", "subquery_slug", "base_query_slug", "kpi_imagem_base64", "kpi_imagem_mime",
    "parametros", "agrupamentos", "agregacoes", "subquery_parametros",
]
```

- [x] **Step 6: Checar dependência ausente no `_checar_dependencias`**

Em `backend/services/portabilidade.py`, dentro do loop de `for q in bundle["queries"]:` que já checa `subquery_slug` (linhas 348-352), adicionar logo depois:

```python
        if q.get("base_query_slug") and not await query_ok(q["base_query_slug"]):
            faltando.append(f"query base '{q['base_query_slug']}'")
```

- [x] **Step 7: Resolver o vínculo no import (passo 2, mesmo padrão de `_set_subquery`)**

Adicionar uma função nova logo depois de `_set_subquery` (depois da linha 438):

```python
async def _set_query_base(conn, slug: str, empresa_slug, base_slug: str, base_empresa_slug):
    emp_id = await _empresa_id_de_slug(empresa_slug)
    base_emp_id = await _empresa_id_de_slug(base_empresa_slug)
    base = await conn.fetch(
        "SELECT id FROM queries WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
        base_slug, base_emp_id)
    base_id = base[0]["id"] if base else None
    await conn.execute(
        "UPDATE queries SET query_base_id = $1 WHERE slug = $2 AND empresa_id IS NOT DISTINCT FROM $3",
        base_id, slug, emp_id)
```

Em `importar_bundle`, logo depois do loop que resolve `subquery_slug`/limpa `subquery_id` obsoleto (linhas 568-583), adicionar um loop análogo:

```python
        for qb in bundle["queries"]:
            if qb["slug"] not in aplicar_qry:
                continue
            if qb.get("base_query_slug"):
                base_entry = por_slug.get(qb["base_query_slug"])
                base_emp_slug = base_entry.get("empresa_slug") if base_entry else qb.get("empresa_slug")
                await _set_query_base(conn, qb["slug"], qb.get("empresa_slug"),
                                      qb["base_query_slug"], base_emp_slug)
            else:
                emp_id = await _empresa_id_de_slug(qb.get("empresa_slug"))
                await conn.execute(
                    "UPDATE queries SET query_base_id = NULL "
                    "WHERE slug = $1 AND empresa_id IS NOT DISTINCT FROM $2",
                    qb["slug"], emp_id)
```

- [x] **Step 8: Rodar e confirmar que passam**

```bash
docker exec datahub_backend python -m pytest tests/test_portabilidade_paineis.py -v
```

Expected: todos os testes de portabilidade (novos + pré-existentes) em PASS.

- [x] **Step 9: Rodar a suíte completa**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```

Expected: sem regressão.

- [x] **Step 10: Commit**

```bash
git add backend/services/portabilidade.py backend/tests/test_portabilidade_paineis.py
git commit -m "feat: portabilidade leva query_base_id como dependência transitiva (export/analisar/importar)"
```

---

### Task 5: Frontend — seletor "Query base" nas telas de query

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`

**Interfaces:**
- Consumes: `GET/POST/PATCH /api/queries` com `query_base_id` (Task 3); `GET /api/queries/{id}/parametros` (já existe).
- Produces: nenhuma interface nova pra outras tasks — é a ponta da cadeia.

- [x] **Step 1: `nova/+page.svelte` — estado**

Em `frontend/src/routes/configuracoes/queries/nova/+page.svelte:22` (logo após `subquery_id: null,` dentro de `form`), adicionar:

```js
    query_base_id: null,
```

Logo após a declaração de `let mapeamentoSubquery = [];` (linha 51), adicionar:

```js
  let baseParams = []; // parâmetros ($1..) da query base escolhida, com _testar_valor local
```

- [x] **Step 2: `nova/+page.svelte` — handler de troca de base**

Logo depois de `onSubqueryChange` (depois da linha 145), adicionar:

```js
  async function onBaseQueryChange() {
    if (!form.query_base_id) {
      baseParams = [];
      return;
    }
    const fetched = await api.parametrosQuery(form.query_base_id);
    baseParams = fetched.map(p => ({ ...p, _testar_valor: '' }));
  }
```

- [x] **Step 3: `nova/+page.svelte` — `testar()` usa os parâmetros certos**

Trocar `testar()` (linhas 147-161) por:

```js
  async function testar(sql) {
    const origem = form.query_base_id ? baseParams : params;
    const testar_parametros = origem.map(p => ({
      nome:  p.nome,
      valor: p._testar_valor !== '' ? p._testar_valor : (p.valor_padrao || null)
    }));

    const res = await api.testarQuery({
      ...form,
      sql_texto: sql,
      testar_empresa_id: testarEmpresaId,
      testar_parametros,
    });
    resultadoTeste = res;
    return res;
  }
```

- [x] **Step 4: `nova/+page.svelte` — UI do seletor**

Logo antes do comentário `<!-- Parâmetros -->` (linha 567), inserir um novo bloco:

```svelte
    <div class="section-block">
      <span class="section-title">Query base (opcional)</span>
      <label class="lbl">
        Reaproveitar o FROM/JOIN de outra query já cadastrada
        <select bind:value={form.query_base_id} on:change={onBaseQueryChange}>
          <option value={null}>— nenhuma (SQL completo abaixo) —</option>
          {#each queriesDisponiveis.filter(q => !q.query_base_id && q.slug !== form.slug) as q}
            <option value={q.id}>{q.nome} ({q.slug})</option>
          {/each}
        </select>
      </label>
      {#if form.query_base_id}
        <p class="hint-block">
          Escreva o SQL abaixo como se <code>base</code> já fosse uma tabela — sem repetir
          FROM/JOIN/filtros. Os parâmetros abaixo (da base) já estão disponíveis dentro da CTE;
          não precisa recriá-los na seção "Parâmetros".
        </p>
        {#if baseParams.length > 0}
          <div class="params-table">
            {#each baseParams as p, i}
              <div class="params-row">
                <span class="pos-badge">${'{'}i + 1{'}'}</span>
                <span>{p.nome}</span>
                <input class="input-teste" bind:value={baseParams[i]._testar_valor} placeholder="valor p/ teste" />
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>

```

- [x] **Step 5: `[id]/+page.svelte` — estado**

Em `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:25` (logo após `subquery_id: null,`), adicionar:

```js
    query_base_id: null,
```

Logo após `let mapeamentoSubquery = [];` (linha 56), adicionar:

```js
  let baseParams = [];
```

- [x] **Step 6: `[id]/+page.svelte` — carregar valor existente no `onMount`**

Em `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:108` (logo após `subquery_id: q.subquery_id ?? null,` dentro do objeto `form` montado no `onMount`), adicionar:

```js
        query_base_id:      q.query_base_id ?? null,
```

Logo depois do bloco `if (q.tipo === 'table_dynamic') { ... }` (depois da linha 129, antes do `} catch`), adicionar:

```js
      if (q.query_base_id) {
        const fetched = await api.parametrosQuery(q.query_base_id);
        baseParams = fetched.map(p => ({ ...p, _testar_valor: '' }));
      }
```

- [x] **Step 7: `[id]/+page.svelte` — handler de troca de base**

Logo depois de `onSubqueryChange` (depois da linha 203), adicionar:

```js
  async function onBaseQueryChange() {
    if (!form.query_base_id) {
      baseParams = [];
      return;
    }
    const fetched = await api.parametrosQuery(form.query_base_id);
    baseParams = fetched.map(p => ({ ...p, _testar_valor: '' }));
  }
```

- [x] **Step 8: `[id]/+page.svelte` — `testar()` usa os parâmetros certos**

Trocar `testar()` (linhas 205-219) por:

```js
  async function testar(sql) {
    const origem = form.query_base_id ? baseParams : params;
    const testar_parametros = origem.map(p => ({
      nome:  p.nome,
      valor: p._testar_valor !== '' ? p._testar_valor : (p.valor_padrao || null)
    }));

    const res = await api.testarQuery({
      ...form,
      sql_texto: sql,
      testar_empresa_id: testarEmpresaId,
      testar_parametros,
    });
    resultadoTeste = res;
    return res;
  }
```

- [x] **Step 9: `[id]/+page.svelte` — UI do seletor**

Logo antes do comentário `<!-- Parâmetros -->` (linha 673), inserir:

```svelte
    <div class="section-block">
      <span class="section-title">Query base (opcional)</span>
      <label class="lbl">
        Reaproveitar o FROM/JOIN de outra query já cadastrada
        <select bind:value={form.query_base_id} on:change={onBaseQueryChange}>
          <option value={null}>— nenhuma (SQL completo abaixo) —</option>
          {#each queriesDisponiveis.filter(q => !q.query_base_id && q.slug !== form.slug) as q}
            <option value={q.id}>{q.nome} ({q.slug})</option>
          {/each}
        </select>
      </label>
      {#if form.query_base_id}
        <p class="hint-block">
          Escreva o SQL abaixo como se <code>base</code> já fosse uma tabela — sem repetir
          FROM/JOIN/filtros. Os parâmetros abaixo (da base) já estão disponíveis dentro da CTE;
          não precisa recriá-los na seção "Parâmetros".
        </p>
        {#if baseParams.length > 0}
          <div class="params-table">
            {#each baseParams as p, i}
              <div class="params-row">
                <span class="pos-badge">${'{'}i + 1{'}'}</span>
                <span>{p.nome}</span>
                <input class="input-teste" bind:value={baseParams[i]._testar_valor} placeholder="valor p/ teste" />
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>

```

- [x] **Step 10: `[id]/+page.svelte` — incluir no payload de `atualizar_query`**

Diferente da tela `nova` (que manda `form` inteiro), `salvar()` em `[id]/+page.svelte` monta o payload campo a campo. Em `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:261` (logo após `subquery_id: form.subquery_id,`), adicionar:

```js
        query_base_id:      form.query_base_id,
```

- [x] **Step 11: Verificação manual via browser (sem framework de teste no frontend)**

```bash
docker restart datahub_frontend
```

Depois, via `mcp__claude-in-chrome__*` (carregar as ferramentas com `ToolSearch` se ainda não estiverem carregadas) ou navegação manual:

1. Login em `http://localhost:3000` (`admin@datahub.local` / `admin123`, empresa `alpha`).
2. `/configuracoes/queries/nova`: criar uma query `tipo=table`, `sql_texto = SELECT 1 AS grupo, 10 AS valor`, salvar.
3. Criar uma segunda query, escolher a primeira no seletor "Query base", `sql_texto = SELECT grupo, valor FROM base`, clicar "Testar" — confirmar que a amostra mostra `{grupo: 1, valor: 10}` sem erro.
4. Salvar a segunda query, abrir `/configuracoes/queries/{id}` dela e confirmar que o seletor "Query base" já vem preenchido com a primeira.
5. Apagar as duas queries de teste.

- [x] **Step 12: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/nova/+page.svelte frontend/src/routes/configuracoes/queries/[id]/+page.svelte
git commit -m "feat: seletor de query base nas telas de nova/editar query"
```

---

### Task 6: Migração piloto — grupo Pendência (30 queries → 3 bases + 30 derivadas)

**Files:**
- Banco `datahub_meta` (dev), via `docker exec datahub_postgres psql`

**Interfaces:**
- Consumes: mecanismo completo das Tasks 1-4 (schema + `resolver_query` + validação de `criar_query`).
- Produces: nenhuma — é o piloto real, consumido só por verificação manual/visual.

- [x] **Step 1: Conferir o estado atual (baseline antes de migrar)**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
SELECT count(*) AS total, sum(length(sql_texto)) AS bytes
FROM queries WHERE slug LIKE 'pen_pendencias_%' AND ativo = true;"
```

Expected: `total = 30`, `bytes` próximo de 70000 (baseline documentado no spec).

- [x] **Step 2: Criar as 3 queries base**

```bash
cat <<'EOF' > /tmp/migracao_pendencia_bases.sql
\set ON_ERROR_STOP on
BEGIN;

INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_pendencia', 'Base — Pendências (PENDENCIA)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos'),
$sql$
SELECT
  this_.pendencia_id                          AS pendencia_id,
  this_.mob_pend_id                           AS "ID",
  upper(this_.descricao)                      AS "Descrição Pendência",
  this_.situacao_pendencia                    AS situacao_pendencia,
  tv.tip_veic_id                              AS tip_veic_id,
  tv.descricao                                AS "Tipo Veiculo",
  m.modelo_id                                 AS modelo_id,
  m.descricao                                 AS "Modelo",
  m2.marca_id                                 AS marca_id,
  m2.descricao                                AS "Marca",
  v.veiculo_id                                AS veiculo_id,
  v.placa                                     AS placa,
  v.prefixo                                   AS prefixo,
  f2.frente_trabalho_id                       AS frente_trabalho_id,
  f2.descricao                                AS frente_trabalho_descricao,
  s3.sistema_id                               AS sistema_id,
  s3.descricao                                AS sistema_descricao,
  floor((DATE_PART('DAY',(coalesce(data_realizada,now())-data_abertura))*24)
    + (extract(HOUR FROM(coalesce(data_realizada, now())-data_abertura)))
    + (extract(MINUTE FROM(coalesce(data_realizada, now())-data_abertura))/60)) AS "Horas Pendente",
  floor((DATE_PART('DAY',(coalesce(data_autorizada,now())-data_abertura))*24)
    + (extract(hour from (coalesce(data_autorizada, now())-data_abertura)))
    + (extract(MINUTE FROM (coalesce(data_autorizada, now())-data_abertura))/60)) AS "Horas Aguard. Autorização",
  floor(coalesce((DATE_PART('DAY',(coalesce(data_realizada, now())-data_autorizada))*24)
    + (extract(HOUR FROM (coalesce(data_realizada, now())-data_autorizada)))
    + (extract(MINUTE FROM (coalesce(data_realizada, now())-data_autorizada))/60),0)) AS "Horas Aguard. Manutenção"
FROM pendencia this_
left outer join pessoa p on this_.pessoa_id=p.pessoa_id
left outer join propriedade p2 on this_.propriedade_id=p2.propriedade_id
left outer join setor s on this_.setor_id=s.setor_id
left outer join sub_sistema s2 on this_.subsistema_id=s2.sub_sistema_id
left outer join sistema s3 on s2.sistema_id=s3.sistema_id
left outer join talhao t on this_.talhao_id=t.talhao_id
left outer join usuario u on this_.usuario_cadastro_id=u.usuario_id
left outer join funcionario f on u.usuario_id=f.funcionario_id
left outer join veiculo v on this_.veiculo_id=v.veiculo_id
left outer join hist_alocacao h on v.veiculo_id = h.veiculo_id
left outer join frente_trabalho f2 on h.frente_trabalho_id=f2.frente_trabalho_id
left outer join modelo m on v.modelo_id=m.modelo_id
left outer join marca m2 on m.marca_id=m2.marca_id
left outer join tipo_veiculo tv on v.tip_veic_id=tv.tip_veic_id
where cast(this_.data_abertura as DATE) between $1 and $2
and h.data_inicio<=this_.data_cadastro and (h.data_fim>=this_.data_cadastro or h.data_fim is null)
and ($3::text is null or f.funcionario_id = any(string_to_array($3, ',')::bigint[]))
and ($4::text is null or v.veiculo_id = any(string_to_array($4, ',')::bigint[]))
and ($5::text is null or tv.tip_veic_id = any(string_to_array($5, ',')::bigint[]))
and ($6::text is null or m2.marca_id = any(string_to_array($6, ',')::bigint[]))
and ($7::text is null or m.modelo_id = any(string_to_array($7, ',')::bigint[]))
and ($8::text is null or s3.sistema_id = any(string_to_array($8, ',')::bigint[]))
and ($9::text is null or s2.sub_sistema_id = any(string_to_array($9, ',')::bigint[]))
and exists (select 'x' from frente_trabalho_func c where c.frente_trabalho_id = h.frente_trabalho_id and c.funcionario_id::text = $10)
and ($11::text is null or f2.frente_trabalho_id = any(string_to_array($11, ',')::bigint[]))
and ($12::text is null or this_.situacao_pendencia = any(string_to_array($12, ',')))
and tipo = 'PENDENCIA'
$sql$
RETURNING id AS base_pendencia_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_pendencia_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_lancamentos');

-- SEDE: mesmo SQL, só o literal final muda
INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_sede', 'Base — Pendências (SEDE)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos_sede'),
       replace(sql_texto, $$tipo = 'PENDENCIA'$$, $$tipo = 'SEDE'$$)
FROM queries WHERE slug = 'pen_pendencias_base_pendencia'
RETURNING id AS base_sede_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_sede_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = :base_pendencia_id;

-- LAVOURA: idem
INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_lavoura', 'Base — Pendências (LAVOURA)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos_lavoura'),
       replace(sql_texto, $$tipo = 'PENDENCIA'$$, $$tipo = 'LAVOURA'$$)
FROM queries WHERE slug = 'pen_pendencias_base_pendencia'
RETURNING id AS base_lavoura_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_lavoura_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = :base_pendencia_id;

COMMIT;
SELECT :base_pendencia_id AS base_pendencia_id, :base_sede_id AS base_sede_id, :base_lavoura_id AS base_lavoura_id;
EOF
cat /tmp/migracao_pendencia_bases.sql | docker exec -i datahub_postgres psql -U postgres -d datahub_meta -v ON_ERROR_STOP=1
```

- [x] **Step 3: Verificar que as 3 bases retornam dado real**

```bash
docker exec datahub_backend python -c "
import asyncio
from services.query_runner import resolver_query

async def main():
    for slug in ['pen_pendencias_base_pendencia', 'pen_pendencias_base_sede', 'pen_pendencias_base_lavoura']:
        r = await resolver_query(slug=slug, company_slug='prats', empresa_id=2, parametros={'data_inicio':'2026-01-01','data_fim':'2026-09-16'})
        print(slug, '->', len(r['data']), 'linhas, ok' if 'erro' not in r else r)

asyncio.run(main())
"
```

Expected: as 3 rodam sem exceção (contagem de linhas pode ser 0 se o filtro obrigatório `$10` não for passado — mesmo comportamento que as queries originais já tinham antes da migração, não é regressão).

- [x] **Step 4: Reescrever as 30 derivadas — tabela de mapeamento (slug → SQL derivado)**

Pra cada um dos 3 sufixos (`''` = tipo PENDENCIA original sem sufixo, `_sede`, `_lavoura`), rodar o bloco abaixo trocando `<SUF>` pelo sufixo e `<BASESLUG>` pela base correspondente (`pen_pendencias_base_pendencia` / `pen_pendencias_base_sede` / `pen_pendencias_base_lavoura`). Primeiro o bloco pra `<SUF> = ''` (as 10 originais, sem sufixo no slug — conferir os slugs exatos com `docker exec datahub_postgres psql -U postgres -d datahub_meta -c "SELECT slug FROM queries WHERE grupo_id = (SELECT grupo_id FROM queries WHERE slug='pen_pendencias_lancamentos') AND slug NOT LIKE '%_sede' AND slug NOT LIKE '%_lavoura' AND slug NOT LIKE '%_base_%';"` antes de rodar, pra confirmar que são exatamente os 10 esperados: `pen_pendencias_pendente_equip`, `pen_pendencias_aguar_manut_equip`, `pen_pendencias_finalizadas_equip`, `pen_pendencias_por_frente`, `pen_pendencias_percentual_sit`, `pen_pendencias_por_sistemas_em_aberto`, `pen_pendencias_por_tipo_equip`, `pen_pendencias_por_tipo_marca`, `pen_pendencias_por_tipo_modelo`, `pen_pendencias_lancamentos`):

```bash
cat <<'EOF' > /tmp/migracao_pendencia_derivadas.sql
\set ON_ERROR_STOP on
BEGIN;

-- helper: pega o id da base pelo slug (roda 1x, reaproveitado nas 3 rodadas abaixo)
-- Rodada 1: tipo PENDENCIA (slugs sem sufixo) -> base = pen_pendencias_base_pendencia
-- Rodada 2: sufixo _sede                       -> base = pen_pendencias_base_sede
-- Rodada 3: sufixo _lavoura                    -> base = pen_pendencias_base_lavoura
-- (este arquivo cobre a Rodada 1; repetir substituindo slugs/base pras outras 2)

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'$$
WHERE slug = 'pen_pendencias_pendente_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO'$$
WHERE slug = 'pen_pendencias_aguar_manut_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'FINALIZADA'$$
WHERE slug = 'pen_pendencias_finalizadas_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT frente_trabalho_id AS id, frente_trabalho_descricao AS label,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENTE') AS valor,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENCIA_ACOMPANHADA') AS "Pend. Acompanhada",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO') AS "Aguard. Manutenção",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'FINALIZADA') AS "Finalizada"
    FROM base GROUP BY frente_trabalho_id, frente_trabalho_descricao$$
WHERE slug = 'pen_pendencias_por_frente';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT situacao_pendencia,
    CASE WHEN situacao_pendencia = 'PENDENCIA_ACOMPANHADA' THEN 'PEND. ACOMPANHADA'
         WHEN situacao_pendencia = 'AGUARDANDO_MANUTENCAO' THEN 'AGUARD. MANUTENÇÃO'
         ELSE situacao_pendencia END AS label,
    ROUND(COUNT(DISTINCT pendencia_id) * 100.0 / SUM(COUNT(DISTINCT pendencia_id)) OVER (), 2) AS valor
    FROM base GROUP BY situacao_pendencia
    ORDER BY CASE situacao_pendencia
      WHEN 'PENDENTE' THEN 1 WHEN 'PENDENCIA_ACOMPANHADA' THEN 2
      WHEN 'AGUARDANDO_MANUTENCAO' THEN 3 WHEN 'FINALIZADA' THEN 4 ELSE 99 END$$
WHERE slug = 'pen_pendencias_percentual_sit';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT sistema_id, sistema_descricao AS label, count(distinct pendencia_id) AS valor
    FROM base WHERE situacao_pendencia = 'PENDENTE' GROUP BY sistema_id, sistema_descricao ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_sistemas_em_aberto';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT marca_id, "Marca" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY marca_id, "Marca" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_marca';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT modelo_id, "Modelo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY modelo_id, "Modelo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_modelo';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT "ID", "Descrição Pendência", "Tipo Veiculo", "Modelo", "Marca", placa, prefixo, "Horas Pendente", "Horas Aguard. Autorização", "Horas Aguard. Manutenção" FROM base$$
WHERE slug = 'pen_pendencias_lancamentos';

-- Esvazia os parâmetros das 10 derivadas (agora vivem só na base)
DELETE FROM query_parametros WHERE query_id IN (
  SELECT id FROM queries WHERE slug IN (
    'pen_pendencias_pendente_equip', 'pen_pendencias_aguar_manut_equip', 'pen_pendencias_finalizadas_equip',
    'pen_pendencias_por_frente', 'pen_pendencias_percentual_sit', 'pen_pendencias_por_sistemas_em_aberto',
    'pen_pendencias_por_tipo_equip', 'pen_pendencias_por_tipo_marca', 'pen_pendencias_por_tipo_modelo',
    'pen_pendencias_lancamentos'
  )
);

COMMIT;
EOF
cat /tmp/migracao_pendencia_derivadas.sql | docker exec -i datahub_postgres psql -U postgres -d datahub_meta -v ON_ERROR_STOP=1
```

- [x] **Step 5: Repetir o Step 4 pras 10 queries `_sede`**

Copiar `/tmp/migracao_pendencia_derivadas.sql` pra `/tmp/migracao_pendencia_derivadas_sede.sql`, e nesse novo arquivo:
- trocar toda ocorrência de `'pen_pendencias_base_pendencia'` por `'pen_pendencias_base_sede'`;
- trocar cada `WHERE slug = 'pen_pendencias_X'` por `WHERE slug = 'pen_pendencias_X_sede'` (10 ocorrências no bloco de `UPDATE`, mais a lista dentro do `DELETE FROM query_parametros`, que passa a listar os 10 slugs com sufixo `_sede`).

Rodar do mesmo jeito:

```bash
cat /tmp/migracao_pendencia_derivadas_sede.sql | docker exec -i datahub_postgres psql -U postgres -d datahub_meta -v ON_ERROR_STOP=1
```

- [x] **Step 6: Repetir o Step 4 pras 10 queries `_lavoura`**

Mesma coisa, com `pen_pendencias_base_lavoura` e sufixo `_lavoura`.

```bash
cat /tmp/migracao_pendencia_derivadas_lavoura.sql | docker exec -i datahub_postgres psql -U postgres -d datahub_meta -v ON_ERROR_STOP=1
```

- [x] **Step 7: Verificar o tamanho final do grupo**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
SELECT count(*) AS total, sum(length(sql_texto)) AS bytes
FROM queries WHERE (slug LIKE 'pen_pendencias_%' OR slug LIKE 'pen_pendencias_base_%') AND ativo = true;"
```

Expected: `total = 33` (3 bases + 30 derivadas), `bytes` bem menor que os ~70000 do baseline (Step 1) — próximo dos ~13-15KB estimados no spec.

- [x] **Step 8: Comparar resultado antes/depois pra cada uma das 30 derivadas**

```bash
docker exec datahub_backend python -c "
import asyncio
from services.query_runner import resolver_query

SLUGS = [
    'pen_pendencias_pendente_equip', 'pen_pendencias_aguar_manut_equip', 'pen_pendencias_finalizadas_equip',
    'pen_pendencias_por_frente', 'pen_pendencias_percentual_sit', 'pen_pendencias_por_sistemas_em_aberto',
    'pen_pendencias_por_tipo_equip', 'pen_pendencias_por_tipo_marca', 'pen_pendencias_por_tipo_modelo',
    'pen_pendencias_lancamentos',
]
SUFIXOS = ['', '_sede', '_lavoura']

async def main():
    for suf in SUFIXOS:
        for base_slug in SLUGS:
            slug = base_slug if suf == '' else base_slug + suf
            try:
                r = await resolver_query(slug=slug, company_slug='prats', empresa_id=2,
                                          parametros={'data_inicio': '2026-01-01', 'data_fim': '2026-09-16'})
                print(f'{slug}: OK ({len(r[\"data\"])} linhas)')
            except Exception as e:
                print(f'{slug}: ERRO — {e}')

asyncio.run(main())
"
```

Expected: as 30 linhas de saída dizem `OK` (nenhum `ERRO`) — contagem de linhas pode ser 0 pelas mesmas razões já conhecidas (parâmetro `$10` não informado no teste), consistente com o comportamento pré-migração.

- [x] **Step 9: Verificação visual nos 3 painéis reais**

Via browser (`mcp__claude-in-chrome__*`, carregando as ferramentas com `ToolSearch` se preciso):

1. Login como admin em `prats`, abrir `/painel/pen_pendencias_equip`, `/painel/pen_pendencias_sede`, `/painel/pen_pendencias_lavoura`.
2. Em cada um: aplicar o filtro de período, conferir que os 10 cards renderizam sem erro (KPIs, gráfico de frente, % por situação, sistemas em aberto, tipo/marca/modelo, tabela de lançamentos).
3. Clicar num segmento do gráfico "Por Marca" (ou equivalente) e confirmar que o filtro por clique ainda funciona (`filtro_clique_variavel_id` não foi tocado pela migração).

- [x] **Step 10: Commit (registro da migração, sem diff de código)**

Como a migração é só dado (não há arquivo de código pra commitar), registrar no changelog do README ou como nota — não há `git add` de código nesta task. Se o time quiser rastrear isso em algum lugar versionado, anexar os 3 scripts SQL finais (`/tmp/migracao_pendencia_*.sql`) em `scripts/migrations/2026-09-16-pendencia-query-base.sql` (arquivo novo, só de referência — não roda automaticamente):

```bash
cat /tmp/migracao_pendencia_bases.sql /tmp/migracao_pendencia_derivadas.sql /tmp/migracao_pendencia_derivadas_sede.sql /tmp/migracao_pendencia_derivadas_lavoura.sql \
  > scripts/migrations/2026-09-16-pendencia-query-base.sql
git add scripts/migrations/2026-09-16-pendencia-query-base.sql
git commit -m "docs: registra a migração piloto do grupo Pendência pra query base (referência, não roda automático)"
```

---

### Task 7: Verificação final

**Files:** nenhum (só execução)

- [x] **Step 1: Suíte completa do backend**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```

Expected: todos os testes em PASS, incluindo os novos de `test_queries_base.py` e os 2 novos de `test_portabilidade_paineis.py`.

- [x] **Step 2: Confirmar que nenhuma query real fora do piloto foi tocada**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
SELECT count(*) FROM queries WHERE query_base_id IS NOT NULL AND slug NOT LIKE 'pen_pendencias_%' AND slug NOT LIKE 'qb_%' AND slug NOT LIKE 'teste_%';"
```

Expected: `0` — só as 30 derivadas do piloto (e eventuais queries de teste do pytest, já limpas pelos `finally`) têm `query_base_id` setado.

- [x] **Step 3: Resumo pro usuário**

Reportar: bytes de SQL antes/depois do grupo Pendência (Task 6, Steps 1 e 7), confirmação de que os 3 painéis renderizam sem regressão, e lembrete de que este delta de schema (Task 1) ainda precisa ser aplicado manualmente em produção quando o usuário decidir fazer o deploy — mesmo processo de sempre (`README.md` → "Deltas de schema pendentes").
