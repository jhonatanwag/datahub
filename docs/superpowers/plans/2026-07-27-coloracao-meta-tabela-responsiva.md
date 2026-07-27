# Coloração por Meta e Tabela Responsiva Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Em queries tipo `table`: (1) permitir colorir o texto de uma coluna conforme ela estar dentro ou fora de um intervalo de meta (duas outras colunas do próprio SQL, ocultas na tabela); (2) tornar a tabela responsiva no celular (cards empilhados, sem barra de rolagem horizontal).

**Architecture:** Seis colunas novas em `queries` (`meta_habilitada` + 3 nomes de coluna + 2 cores), propagadas por `renderizar_painel` (mesmo padrão de `impressao_*`/`chart_*`), consumidas por `DataTable.svelte` que computa a cor por linha em JS puro e generaliza o filtro de "colunas ocultas" (já existente pro botão de impressão) para incluir as duas colunas de meta. A responsividade é resolvida com duas marcações paralelas (tabela + cards) alternadas por CSS `@media`, sem JS de resize.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, asyncpg, PostgreSQL, pytest

## Global Constraints

- Campos de meta só fazem sentido quando `queries.tipo = 'table'`, mas as colunas existem em todas as linhas (mesmo padrão de `kpi_cor_fonte`/`impressao_*`)
- Limites da meta são inclusivos: `valor >= início AND valor <= fim` conta como dentro
- Sem meta definida (nulo) OU valor/início/fim não numérico → célula com cor padrão, sem colorir (falha silenciosa, não quebra a tabela)
- Só a cor do texto (fonte) muda — fundo da célula não é afetado
- Colunas de meta início/fim nunca aparecem como dado visível na tabela nem no export CSV/Excel; a coluna alvo (colorida) continua visível normalmente
- Sem validação de que as colunas escolhidas existem de fato nos dados retornados — falha silenciosa, mesmo padrão do botão de impressão
- Responsivo: breakpoint `≤768px` (mesmo valor já usado no resto do projeto), layout mobile = cards empilhados (não colunas escondidas automaticamente), sem barra de rolagem horizontal no mobile
- Sem sistema de migrations — `ALTER TABLE` manual + refletir em `scripts/init-db.sql`, `scripts/init-meta-prod.sql` e README ("Deltas de schema pendentes")

---

## Task 1: Backend — campos de meta em `queries`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_queries_meta.py`

**Interfaces:**
- Produces: colunas `queries.meta_habilitada` (BOOLEAN DEFAULT false),
  `meta_coluna_valor`/`meta_coluna_inicio`/`meta_coluna_fim` (TEXT
  nullable), `meta_cor_dentro` (TEXT DEFAULT `'#3fb950'`), `meta_cor_fora`
  (TEXT DEFAULT `'#f85149'`); `QueryInput`/`QueryUpdate` com os 6 campos;
  `POST/PATCH/GET /api/queries/*` passam a incluir os 6 campos na resposta.
- Independente das demais tasks deste plano — pode ser feito primeiro,
  sozinho.

- [ ] **Step 1: Schema (dev + scripts)**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE queries ADD COLUMN meta_habilitada BOOLEAN DEFAULT false; ALTER TABLE queries ADD COLUMN meta_coluna_valor TEXT; ALTER TABLE queries ADD COLUMN meta_coluna_inicio TEXT; ALTER TABLE queries ADD COLUMN meta_coluna_fim TEXT; ALTER TABLE queries ADD COLUMN meta_cor_dentro TEXT DEFAULT '#3fb950'; ALTER TABLE queries ADD COLUMN meta_cor_fora TEXT DEFAULT '#f85149';"
```

Em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`, no bloco
`CREATE TABLE queries`, adicionar logo após `impressao_coluna TEXT,`:

```sql
    meta_habilitada    BOOLEAN DEFAULT false,
    meta_coluna_valor  TEXT,
    meta_coluna_inicio TEXT,
    meta_coluna_fim    TEXT,
    meta_cor_dentro    TEXT DEFAULT '#3fb950',
    meta_cor_fora      TEXT DEFAULT '#f85149'
```

Em `README.md`, seção "Deltas de schema pendentes", adicionar ao bloco de
`SELECT column_name ... WHERE table_name = 'queries'`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'queries'
  AND column_name IN ('mapa_camada', 'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor', 'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna', 'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio', 'meta_coluna_fim', 'meta_cor_dentro', 'meta_cor_fora');
```

E no bloco de `ALTER TABLE` a aplicar:

```sql
-- 2026-07-27 — coloração condicional de uma coluna por meta (início/fim), queries tipo table
ALTER TABLE queries ADD COLUMN meta_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN meta_coluna_valor TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_inicio TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_fim TEXT;
ALTER TABLE queries ADD COLUMN meta_cor_dentro TEXT DEFAULT '#3fb950';
ALTER TABLE queries ADD COLUMN meta_cor_fora TEXT DEFAULT '#f85149';
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_queries_meta.py`:

```python
TABLE_SQL = "SELECT 50 AS valor, 10 AS meta_inicio, 100 AS meta_fim"


def test_criar_query_table_com_meta_habilitada(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_habilitada",
            "nome": "Teste Meta",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
            "meta_cor_dentro": "#00ff00",
            "meta_cor_fora": "#ff0000",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is True
    assert body["meta_coluna_valor"] == "valor"
    assert body["meta_coluna_inicio"] == "meta_inicio"
    assert body["meta_coluna_fim"] == "meta_fim"
    assert body["meta_cor_dentro"] == "#00ff00"
    assert body["meta_cor_fora"] == "#ff0000"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_table_sem_meta_fica_com_defaults(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_default",
            "nome": "Teste Meta Default",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is False
    assert body["meta_coluna_valor"] is None
    assert body["meta_coluna_inicio"] is None
    assert body["meta_coluna_fim"] is None
    assert body["meta_cor_dentro"] == "#3fb950"
    assert body["meta_cor_fora"] == "#f85149"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_campos_de_meta(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_meta_update",
            "nome": "Teste",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    query_id = criar.json()["id"]

    res = client.patch(
        f"/api/queries/{query_id}",
        json={
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meta_habilitada"] is True
    assert body["meta_coluna_valor"] == "valor"
    assert body["meta_coluna_inicio"] == "meta_inicio"
    assert body["meta_coluna_fim"] == "meta_fim"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_meta.py -v`
Expected: FAIL — os 6 campos não existem em `QueryInput`/`QueryUpdate`,
então são descartados pelo Pydantic e não aparecem na resposta.

- [ ] **Step 4: Implement — `backend/routes/queries.py`**

`QueryInput`: adicionar (após `impressao_coluna: Optional[str] = None`):

```python
    meta_habilitada: bool = False
    meta_coluna_valor: Optional[str] = None
    meta_coluna_inicio: Optional[str] = None
    meta_coluna_fim: Optional[str] = None
    meta_cor_dentro: Optional[str] = '#3fb950'
    meta_cor_fora: Optional[str] = '#f85149'
```

`QueryUpdate`: os mesmos 6 campos, todos `Optional`/default `None`:

```python
    meta_habilitada: Optional[bool] = None
    meta_coluna_valor: Optional[str] = None
    meta_coluna_inicio: Optional[str] = None
    meta_coluna_fim: Optional[str] = None
    meta_cor_dentro: Optional[str] = None
    meta_cor_fora: Optional[str] = None
```

`atualizar_query` — incluir os 6 em `ALLOWED_COLS`:

```python
        ALLOWED_COLS = {
            'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo',
            'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada',
            'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor',
            'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna',
            'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio', 'meta_coluna_fim',
            'meta_cor_dentro', 'meta_cor_fora'
        }
```

`criar_query` — incluir no INSERT (agora 25 colunas):

```python
        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor,
                chart_valor_label, impressao_habilitada, impressao_caminho, impressao_coluna,
                meta_habilitada, meta_coluna_valor, meta_coluna_inicio, meta_coluna_fim,
                meta_cor_dentro, meta_cor_fora
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
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
            body.meta_cor_dentro, body.meta_cor_fora)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_meta.py -v`
Expected: PASS

- [ ] **Step 6: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: all tests pass (no regressions in the shared `queries.py` CRUD
paths other tests exercise).

- [ ] **Step 7: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md backend/routes/queries.py backend/tests/test_queries_meta.py
git commit -m "feat: add meta-based coloring config fields to queries"
```

---

## Task 2: Backend — propagar os campos de meta em `renderizar_painel`

**Files:**
- Modify: `backend/routes/paineis.py`
- Test: `backend/tests/test_paineis_meta.py`

**Interfaces:**
- Consumes: as 6 colunas `queries.meta_*` (Task 1) — precisa estar
  concluída antes deste task.
- Produces: cada item de `GET /api/paineis/{id}/renderizar` →
  `indicadores[]` inclui `meta_habilitada`, `meta_coluna_valor`,
  `meta_coluna_inicio`, `meta_coluna_fim`, `meta_cor_dentro`,
  `meta_cor_fora`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_paineis_meta.py`:

```python
import uuid
from conftest import hard_delete_painel


def test_renderizar_painel_inclui_campos_de_meta_do_indicador(client, auth_token):
    query_slug = f"query_meta_painel_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Meta Painel",
            "sql_texto": "SELECT 50 AS valor, 10 AS meta_inicio, 100 AS meta_fim",
            "tipo": "table",
            "cache_ttl": 0,
            "meta_habilitada": True,
            "meta_coluna_valor": "valor",
            "meta_coluna_inicio": "meta_inicio",
            "meta_coluna_fim": "meta_fim",
            "meta_cor_dentro": "#00ff00",
            "meta_cor_fora": "#ff0000",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    painel_slug = f"painel_meta_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Meta"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert painel_res.status_code == 200
    painel_id = painel_res.json()["id"]

    ind_res = client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ind_res.status_code == 200

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        indicador = res.json()["indicadores"][0]
        assert indicador["meta_habilitada"] is True
        assert indicador["meta_coluna_valor"] == "valor"
        assert indicador["meta_coluna_inicio"] == "meta_inicio"
        assert indicador["meta_coluna_fim"] == "meta_fim"
        assert indicador["meta_cor_dentro"] == "#00ff00"
        assert indicador["meta_cor_fora"] == "#ff0000"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_meta.py -v`
Expected: FAIL — os campos `meta_*` ainda não estão no `SELECT` de
`renderizar_painel`, então não aparecem no indicador retornado.

- [ ] **Step 3: Implement — `backend/routes/paineis.py`**

Em `renderizar_painel`, incluir as 6 colunas no `SELECT` que já traz
`impressao_habilitada` etc.:

```python
    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label, q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna,
               q.meta_habilitada, q.meta_coluna_valor, q.meta_coluna_inicio, q.meta_coluna_fim,
               q.meta_cor_dentro, q.meta_cor_fora
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_meta.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/paineis.py backend/tests/test_paineis_meta.py
git commit -m "feat: propagate meta-coloring fields through renderizar_painel"
```

---

## Task 3: Frontend — config UI + coloração em `DataTable.svelte`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`
- Modify: `frontend/src/lib/components/DataTable.svelte`
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `ind.meta_*` de cada indicador retornado por `renderizar_painel`
  (Task 2) — precisa estar concluída antes deste task.
- Produces: `DataTable.svelte` ganha props `metaHabilitada`,
  `metaColunaValor`, `metaColunaInicio`, `metaColunaFim`, `metaCorDentro`,
  `metaCorFora`, uma função `corMeta(row)`, e um conjunto generalizado de
  "colunas ocultas" (`colunasOcultas`) que o Task 4 (cards mobile) também
  vai consumir.
- Sem testes automatizados — projeto não tem framework de teste de
  frontend. Verificação manual via navegador (Step 6).

- [ ] **Step 1: Tela de query — seção "Coloração por Meta"**

`frontend/src/routes/configuracoes/queries/nova/+page.svelte`:

No `form`, adicionar após `impressao_coluna: ''`:

```js
    meta_habilitada: false, meta_coluna_valor: '', meta_coluna_inicio: '',
    meta_coluna_fim: '', meta_cor_dentro: '#3fb950', meta_cor_fora: '#f85149'
```

Logo depois do bloco `{#if form.tipo === 'table'}` existente (o do "Botão
de Impressão" — este novo bloco fica **dentro do mesmo tipo de query**, mas
como um `<div class="section-block">` irmão, no mesmo nível do bloco de
impressão, não aninhado dentro dele):

```svelte
    {#if form.tipo === 'table'}
      <div class="section-block">
        <span class="section-title">Coloração por Meta</span>
        <label class="check-inline">
          <input type="checkbox" bind:checked={form.meta_habilitada} />
          Colorir uma coluna conforme uma meta (início/fim)
        </label>
        {#if form.meta_habilitada}
          <label class="lbl">
            Coluna a colorir (continua visível na tabela)
            <select bind:value={form.meta_coluna_valor}>
              <option value="">— selecione —</option>
              {#each resultadoTeste?.colunas ?? (form.meta_coluna_valor ? [form.meta_coluna_valor] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
          </label>
          <label class="lbl">
            Coluna com o início da meta (fica oculta na tabela)
            <select bind:value={form.meta_coluna_inicio}>
              <option value="">— selecione —</option>
              {#each resultadoTeste?.colunas ?? (form.meta_coluna_inicio ? [form.meta_coluna_inicio] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
          </label>
          <label class="lbl">
            Coluna com o fim da meta (fica oculta na tabela)
            <select bind:value={form.meta_coluna_fim}>
              <option value="">— selecione —</option>
              {#each resultadoTeste?.colunas ?? (form.meta_coluna_fim ? [form.meta_coluna_fim] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
          </label>
          <div class="cores-row">
            <label class="lbl">
              Cor dentro da meta
              <div class="color-pick">
                <input type="color" bind:value={form.meta_cor_dentro} />
                <input type="text"  bind:value={form.meta_cor_dentro} placeholder="#3fb950" style="width:90px" />
              </div>
            </label>
            <label class="lbl">
              Cor fora da meta
              <div class="color-pick">
                <input type="color" bind:value={form.meta_cor_fora} />
                <input type="text"  bind:value={form.meta_cor_fora} placeholder="#f85149" style="width:90px" />
              </div>
            </label>
          </div>
          <p class="hint-block">
            Se o valor da coluna escolhida estiver entre início e fim (incluindo os limites), o texto
            fica na "cor dentro da meta"; fora disso, na "cor fora da meta". Linha sem meta definida ou
            com valor não numérico fica com a cor padrão, sem indicar dentro/fora.
          </p>
        {/if}
      </div>
    {/if}
```

Incluir os 6 campos no payload de `criarQuery` — já coberto automaticamente
(`salvar()` envia `form` inteiro pra `api.criarQuery(form)`).

`frontend/src/routes/configuracoes/queries/[id]/+page.svelte`:

No `form` do `onMount`, adicionar após `impressao_coluna: q.impressao_coluna || ''`:

```js
        meta_habilitada:    q.meta_habilitada ?? false,
        meta_coluna_valor:  q.meta_coluna_valor || '',
        meta_coluna_inicio: q.meta_coluna_inicio || '',
        meta_coluna_fim:    q.meta_coluna_fim || '',
        meta_cor_dentro:    q.meta_cor_dentro || '#3fb950',
        meta_cor_fora:      q.meta_cor_fora || '#f85149',
```

Mesmo bloco de template do Step anterior, inserido no mesmo ponto (logo
depois do bloco "Botão de Impressão", 6 espaços de indentação em vez de 4,
mesma observação de aninhamento já aplicada ao bloco de impressão nesse
arquivo):

```svelte
      {#if form.tipo === 'table'}
        <div class="section-block">
          <span class="section-title">Coloração por Meta</span>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.meta_habilitada} />
            Colorir uma coluna conforme uma meta (início/fim)
          </label>
          {#if form.meta_habilitada}
            <label class="lbl">
              Coluna a colorir (continua visível na tabela)
              <select bind:value={form.meta_coluna_valor}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_valor ? [form.meta_coluna_valor] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <label class="lbl">
              Coluna com o início da meta (fica oculta na tabela)
              <select bind:value={form.meta_coluna_inicio}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_inicio ? [form.meta_coluna_inicio] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <label class="lbl">
              Coluna com o fim da meta (fica oculta na tabela)
              <select bind:value={form.meta_coluna_fim}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_fim ? [form.meta_coluna_fim] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <div class="cores-row">
              <label class="lbl">
                Cor dentro da meta
                <div class="color-pick">
                  <input type="color" bind:value={form.meta_cor_dentro} />
                  <input type="text"  bind:value={form.meta_cor_dentro} placeholder="#3fb950" style="width:90px" />
                </div>
              </label>
              <label class="lbl">
                Cor fora da meta
                <div class="color-pick">
                  <input type="color" bind:value={form.meta_cor_fora} />
                  <input type="text"  bind:value={form.meta_cor_fora} placeholder="#f85149" style="width:90px" />
                </div>
              </label>
            </div>
            <p class="hint-block">
              Se o valor da coluna escolhida estiver entre início e fim (incluindo os limites), o texto
              fica na "cor dentro da meta"; fora disso, na "cor fora da meta". Linha sem meta definida ou
              com valor não numérico fica com a cor padrão, sem indicar dentro/fora.
            </p>
          {/if}
        </div>
      {/if}
```

In `salvar()`, add to the `atualizarQuery` payload (which lists fields
explicitly in this file, unlike `nova`):

```js
        meta_habilitada:    form.meta_habilitada,
        meta_coluna_valor:  form.meta_coluna_valor || null,
        meta_coluna_inicio: form.meta_coluna_inicio || null,
        meta_coluna_fim:    form.meta_coluna_fim || null,
        meta_cor_dentro:    form.meta_cor_dentro,
        meta_cor_fora:      form.meta_cor_fora,
```

- [ ] **Step 2: `DataTable.svelte` — props e ocultação generalizada**

Adicionar props novas (após as três `impressao*` já existentes):

```js
  export let metaHabilitada    = false;
  export let metaColunaValor   = null;
  export let metaColunaInicio  = null;
  export let metaColunaFim     = null;
  export let metaCorDentro     = '#3fb950';
  export let metaCorFora       = '#f85149';
```

Trocar o filtro de `colunasEfetivas` (que hoje só exclui `impressaoColuna`)
por um conjunto de colunas ocultas:

```js
  $: colunasOcultas = new Set([
    impressaoHabilitada ? impressaoColuna : null,
    ...(metaHabilitada ? [metaColunaInicio, metaColunaFim] : []),
  ].filter(Boolean));
  $: colunasEfetivas = (colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
  ).filter(c => !colunasOcultas.has(c.key));
```

- [ ] **Step 3: `DataTable.svelte` — cálculo da cor**

Adicionar a função (perto de `fmtValor`/`STATUS_COLOR`):

```js
  function corMeta(row) {
    if (!metaHabilitada || !metaColunaValor || !metaColunaInicio || !metaColunaFim) return null;
    const brutoValor  = row[metaColunaValor];
    const brutoInicio = row[metaColunaInicio];
    const brutoFim    = row[metaColunaFim];
    if (brutoValor == null || brutoInicio == null || brutoFim == null) return null;
    const valor  = Number(brutoValor);
    const inicio = Number(brutoInicio);
    const fim    = Number(brutoFim);
    if (Number.isNaN(valor) || Number.isNaN(inicio) || Number.isNaN(fim)) return null;
    return (valor >= inicio && valor <= fim) ? metaCorDentro : metaCorFora;
  }

  function estiloMeta(row, col) {
    if (col.key !== metaColunaValor) return '';
    const cor = corMeta(row);
    return cor ? `color:${cor}` : '';
  }
```

- [ ] **Step 4: `DataTable.svelte` — aplicar a cor na célula (tabela desktop)**

No `<tbody>`, no `<td>` de cada coluna (dentro do `{#each colunasEfetivas as col}`
existente), adicionar o `style` condicional na tag já existente:

```svelte
            <td style={estiloMeta(row, col)}>
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </td>
```

- [ ] **Step 5: `painel/[slug]/+page.svelte` — passar as novas props**

No `<DataTable>` (mesmo bloco que já passa `impressaoHabilitada` etc.),
adicionar:

```svelte
                metaHabilitada={ind.meta_habilitada}
                metaColunaValor={ind.meta_coluna_valor}
                metaColunaInicio={ind.meta_coluna_inicio}
                metaColunaFim={ind.meta_coluna_fim}
                metaCorDentro={ind.meta_cor_dentro}
                metaCorFora={ind.meta_cor_fora}
```

- [ ] **Step 6: Rebuild dos containers de dev**

```bash
docker restart datahub_backend datahub_frontend
```

- [ ] **Step 7: Verificação manual**

1. Configurações → Queries → nova query tipo `table`, SQL de teste com uma
   coluna de valor e duas de meta (ex:
   `SELECT 50 AS valor, 10 AS meta_inicio, 100 AS meta_fim`). Testar,
   habilitar coloração por meta, selecionar as 3 colunas nos dropdowns,
   deixar as cores padrão. Salvar.
2. Criar um painel, adicionar essa query como indicador, abrir o painel.
3. Confirmar: a tabela mostra só a coluna `valor` (as duas colunas de meta
   ficam ocultas), com o texto na cor verde (`#3fb950`, dentro da meta —
   `50` está entre `10` e `100`).
4. Editar o SQL de teste pra `SELECT 500 AS valor, 10 AS meta_inicio, 100
   AS meta_fim` (fora do intervalo) — confirmar que o texto fica vermelho
   (`#f85149`).
5. Editar o SQL pra `SELECT 50 AS valor, NULL AS meta_inicio, 100 AS
   meta_fim` — confirmar que o texto volta à cor padrão (sem colorir),
   tabela não quebra.
6. Desabilitar a coloração por meta na query — confirmar que a tabela volta
   ao comportamento normal (sem cor condicional).
7. Confirmar que exportar CSV/Excel da tabela ainda funciona e não inclui
   as colunas de meta início/fim (só `valor`, sem estilo — export é texto
   puro).

- [ ] **Step 8: Reverter dados de teste**

Apagar a query e o painel de teste criados no Step 7.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/nova/+page.svelte "frontend/src/routes/configuracoes/queries/[id]/+page.svelte" frontend/src/lib/components/DataTable.svelte "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: add meta-based conditional text coloring to table queries"
```

---

## Task 4: Frontend — tabela responsiva (cards empilhados no mobile)

**Files:**
- Modify: `frontend/src/lib/components/DataTable.svelte`

**Interfaces:**
- Consumes: `colunasEfetivas`, `dadosPaginados`, `corMeta(row)`,
  `mostrarAcoes`, `imprimir(row)`, `STATUS_COLOR`, `fmtValor` — todos já
  existentes em `DataTable.svelte` antes deste task (o `corMeta` vem do
  Task 3, que precisa estar concluído antes deste).
- Produces: layout de cards visível em `≤768px`, tabela normal acima disso
  — nenhuma nova prop pública, só marcação e CSS internos ao componente.
- Sem testes automatizados. Verificação manual via navegador (Step 3).

- [ ] **Step 1: Marcação dos cards (paralela à tabela existente)**

Dentro do `.table-wrap`, logo depois do `</table>` de fechamento e antes da
`<div class="pagination">`, adicionar:

```svelte
  <div class="cards-mobile">
    {#each dadosPaginados as row}
      <div class="card-linha">
        {#if mostrarAcoes && row[impressaoColuna]}
          <button class="btn-ghost btn-sm card-acao" on:click={() => imprimir(row)} title="Imprimir">🖨</button>
        {/if}
        {#each colunasEfetivas as col}
          <div class="card-campo">
            <span class="card-rotulo">{col.label ?? col.key}</span>
            <span
              class="card-valor"
              style={estiloMeta(row, col)}
            >
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </span>
          </div>
        {/each}
      </div>
    {/each}
  </div>
```

- [ ] **Step 2: CSS — alternância por media query + estilos do card**

No bloco `<style>` existente, adicionar:

```css
.cards-mobile { display: none; }

@media (max-width: 768px) {
  table { display: none; }
  .cards-mobile { display: flex; flex-direction: column; gap: 10px; }
  .card-linha {
    position: relative;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .card-acao { position: absolute; top: 8px; right: 8px; }
  .card-campo { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
  .card-rotulo { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
  .card-valor { text-align: right; }
}
```

- [ ] **Step 3: Rebuild e verificação manual**

```bash
docker restart datahub_frontend
```

1. Abrir um painel com uma query tipo `table` (qualquer uma existente, ex:
   `lanc_fichas`) numa janela larga (>768px) — confirmar que a tabela
   continua exatamente como antes (sem cards visíveis).
2. Redimensionar a janela do navegador (ou usar o modo de emulação mobile
   do DevTools) pra ≤768px de largura — confirmar que a tabela vira cards
   empilhados, um por linha, sem barra de rolagem horizontal na página.
3. Cada card mostra todas as colunas como "Rótulo: valor"; se a query tiver
   coloração por meta habilitada (Task 3), o valor da coluna alvo aparece
   com a cor certa dentro do card também.
4. Se a query tiver o botão de impressão habilitado (feature anterior), o
   ícone 🖨 aparece no canto superior direito de cada card e funciona
   (abre o link em nova aba) igual à versão desktop.
5. Paginação, "itens por página" e botões de CSV/Excel continuam visíveis
   e funcionais no mobile, abaixo dos cards.
6. Voltar a largura pra >768px — confirmar que volta pra tabela normal sem
   nenhum resquício visual dos cards.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/DataTable.svelte
git commit -m "feat: make table queries responsive with stacked cards on mobile"
```
