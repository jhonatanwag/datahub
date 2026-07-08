# Configurações de Gráfico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar 4 opções configuráveis aos tipos de gráfico (`chart_bar`, `chart_bar_horizontal`, `chart_line`, `chart_doughnut`) — tamanho de fonte do label, truncamento de texto com limite de caracteres, exibição do valor no gráfico — e suporte automático a múltiplas séries (colunas extras de valor viram barras/linhas adicionais).

**Architecture:** 4 novas colunas em `queries` (mesmo padrão de `kpi_cor_fonte`/`mapa_camada`), expostas no CRUD do backend e propagadas por `renderizar_painel`. `ChartPanel.svelte` detecta séries extras automaticamente a partir das colunas retornadas pela SQL (além de `label`), sem exigir convenção de nomes (`valor1`/`valor2`).

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, ECharts, PostgreSQL, pytest

## Global Constraints

- JS puro — sem TypeScript
- As 4 opções valem para `chart_bar`, `chart_bar_horizontal`, `chart_line`, `chart_doughnut`
- Multi-série (colunas extras viram séries) só se aplica a `chart_bar`, `chart_bar_horizontal`, `chart_line` — `chart_doughnut` ignora colunas além de `valor`
- `axisLabel.interval` deve ser `0` (sempre mostrar todos os rótulos) nos tipos bar/line — é a correção do bug relatado, não uma opção
- Sem validação de range nos campos numéricos novos (`chart_fonte_tamanho`, `chart_truncar_tamanho`) — são inteiros livres, sem enum fechado como `tipo`/`mapa_camada`
- Backend roda em Docker: `datahub_backend`, `datahub_postgres` (banco `datahub_meta`); frontend: `datahub_frontend`
- Sem sistema de migrations — `ALTER TABLE` manual + refletir em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `scripts/init-db.sql` | Modificar | 4 colunas novas em `CREATE TABLE queries` |
| `scripts/init-meta-prod.sql` | Modificar | 4 colunas novas em `CREATE TABLE queries` |
| `backend/routes/queries.py` | Modificar | 4 campos em `QueryInput`/`QueryUpdate`, INSERT, `ALLOWED_COLS` |
| `backend/tests/test_queries_chart_config.py` | Criar | Testes de persistência dos 4 campos novos |
| `backend/routes/paineis.py` | Modificar | Incluir os 4 campos no SELECT de `renderizar_painel` |
| `frontend/src/routes/configuracoes/queries/nova/+page.svelte` | Modificar | Bloco de config de gráfico |
| `frontend/src/routes/configuracoes/queries/[id]/+page.svelte` | Modificar | Idem + incluir no payload do PATCH |
| `frontend/src/lib/components/ChartPanel.svelte` | Modificar | Multi-série, truncamento, fonte, mostrar valor |
| `frontend/src/routes/painel/[slug]/+page.svelte` | Modificar | Passar as 4 props novas pro `ChartPanel` |

---

## Task 1: Schema — 4 colunas de configuração de gráfico

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`

**Interfaces:**
- Produces: colunas `queries.chart_fonte_tamanho` (INTEGER DEFAULT 12), `chart_truncar_label` (BOOLEAN DEFAULT false), `chart_truncar_tamanho` (INTEGER DEFAULT 15), `chart_mostrar_valor` (BOOLEAN DEFAULT false) — base pros Tasks 2 e 3.

- [ ] **Step 1: Aplicar `ALTER TABLE` no Postgres de dev**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
ALTER TABLE queries ADD COLUMN chart_fonte_tamanho INTEGER DEFAULT 12;
ALTER TABLE queries ADD COLUMN chart_truncar_label BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN chart_truncar_tamanho INTEGER DEFAULT 15;
ALTER TABLE queries ADD COLUMN chart_mostrar_valor BOOLEAN DEFAULT false;
"
```

Expected: 4x `ALTER TABLE`

- [ ] **Step 2: Verificar**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "SELECT slug, tipo, chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor FROM queries WHERE tipo LIKE 'chart_%' LIMIT 5;"
```

Expected: linhas existentes mostram `chart_fonte_tamanho=12`, `chart_truncar_label=f`, `chart_truncar_tamanho=15`, `chart_mostrar_valor=f`.

- [ ] **Step 3: Atualizar `scripts/init-db.sql`**

Localizar o bloco `CREATE TABLE queries` (mesmo bloco onde `mapa_camada` foi adicionado) e acrescentar as 4 colunas antes de `UNIQUE (slug, empresa_id)`:

```sql
CREATE TABLE queries (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    sql_texto     TEXT NOT NULL,
    tipo          VARCHAR(30) NOT NULL,
    empresa_id    INTEGER REFERENCES empresas(id) NULL,
    ativo         BOOLEAN DEFAULT true,
    cache_ttl     INTEGER DEFAULT 300,
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    mapa_camada   VARCHAR(20) DEFAULT 'padrao',
    chart_fonte_tamanho   INTEGER DEFAULT 12,
    chart_truncar_label   BOOLEAN DEFAULT false,
    chart_truncar_tamanho INTEGER DEFAULT 15,
    chart_mostrar_valor   BOOLEAN DEFAULT false,
    UNIQUE (slug, empresa_id)
);
```

- [ ] **Step 4: Atualizar `scripts/init-meta-prod.sql`**

Mesmo bloco `CREATE TABLE queries` (onde `kpi_cor_fonte`/`kpi_cor_fundo`/`mapa_camada` já estão):

```sql
CREATE TABLE queries (
    id             SERIAL PRIMARY KEY,
    slug           VARCHAR(100) NOT NULL,
    nome           VARCHAR(150) NOT NULL,
    descricao      TEXT,
    sql_texto      TEXT NOT NULL,
    tipo           VARCHAR(30) NOT NULL,
    empresa_id     INTEGER REFERENCES empresas(id),
    ativo          BOOLEAN DEFAULT true,
    cache_ttl      INTEGER DEFAULT 300,
    criado_em      TIMESTAMP DEFAULT NOW(),
    atualizado_em  TIMESTAMP DEFAULT NOW(),
    kpi_cor_fonte  TEXT DEFAULT '#e6edf3',
    kpi_cor_fundo  TEXT DEFAULT '#161b22',
    mapa_camada    VARCHAR(20) DEFAULT 'padrao',
    chart_fonte_tamanho   INTEGER DEFAULT 12,
    chart_truncar_label   BOOLEAN DEFAULT false,
    chart_truncar_tamanho INTEGER DEFAULT 15,
    chart_mostrar_valor   BOOLEAN DEFAULT false,
    UNIQUE (slug, empresa_id)
);
CREATE INDEX idx_queries_empresa ON queries(empresa_id);
CREATE INDEX idx_queries_slug ON queries(slug);
```

- [ ] **Step 5: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql
git commit -m "feat: add chart config columns to queries table"
```

**Nota para deploy:** este `ALTER TABLE` precisa rodar manualmente no Postgres de produção quando o deploy avançar — mesma pendência já documentada no `README.md` (seção "Deltas de schema pendentes"). Adicionar essas 4 colunas nessa mesma seção do README como parte deste plano seria bom, mas fica pra quando o deploy real acontecer (fora de escopo de tasks de código).

---

## Task 2: Backend — campos de config de gráfico no CRUD de queries

**Files:**
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_queries_chart_config.py`

**Interfaces:**
- Consumes: fixtures `client`/`auth_token` de `backend/tests/conftest.py`
- Produces: `POST`/`PATCH /api/queries` aceitam e persistem `chart_fonte_tamanho`, `chart_truncar_label`, `chart_truncar_tamanho`, `chart_mostrar_valor` — usado pelo frontend nos Tasks 4/5.

- [ ] **Step 1: Escrever os testes (devem falhar — campos ainda não existem)**

Criar `backend/tests/test_queries_chart_config.py`:

```python
CHART_SQL = "SELECT 'A' AS label, 10 AS valor UNION ALL SELECT 'B', 20"


def _criar_query_chart(client, auth_token, slug, **overrides):
    body = {
        "slug": slug,
        "nome": "Teste Config Grafico",
        "sql_texto": CHART_SQL,
        "tipo": "chart_bar",
        **overrides,
    }
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_usa_defaults(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_chart_config_default")
    assert res.status_code == 200
    body = res.json()
    assert body["chart_fonte_tamanho"] == 12
    assert body["chart_truncar_label"] is False
    assert body["chart_truncar_tamanho"] == 15
    assert body["chart_mostrar_valor"] is False
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_com_valores_customizados(client, auth_token):
    res = _criar_query_chart(
        client, auth_token, "teste_chart_config_custom",
        chart_fonte_tamanho=18,
        chart_truncar_label=True,
        chart_truncar_tamanho=8,
        chart_mostrar_valor=True,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["chart_fonte_tamanho"] == 18
    assert body["chart_truncar_label"] is True
    assert body["chart_truncar_tamanho"] == 8
    assert body["chart_mostrar_valor"] is True
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_atualizar_query_chart_config(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_chart_config_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"chart_fonte_tamanho": 20, "chart_mostrar_valor": True},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    body = patch_res.json()
    assert body["chart_fonte_tamanho"] == 20
    assert body["chart_mostrar_valor"] is True
    # campos não enviados no PATCH permanecem com o valor anterior (defaults)
    assert body["chart_truncar_tamanho"] == 15

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_chart_config.py -v
```

Expected: `test_criar_query_chart_usa_defaults` **passa** mesmo sem a Step 3 (a coluna já tem default no Postgres desde a Task 1, e `RETURNING *` já devolve isso independente do código Python — mesma situação já observada na feature de mapa/satélite). `test_criar_query_chart_com_valores_customizados` e `test_atualizar_query_chart_config` **falham**: os valores customizados enviados no `POST`/`PATCH` são ignorados (campos não existem no model Pydantic, e o INSERT não lista essas colunas), então a query é sempre criada com os defaults do banco.

- [ ] **Step 3: Implementar em `backend/routes/queries.py`**

Adicionar os 4 campos no `QueryInput` (logo após `mapa_camada`):

```python
class QueryInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    sql_texto: str
    tipo: str
    empresa_id: Optional[int] = None
    cache_ttl: int = 300
    ativo: bool = True
    kpi_cor_fonte: Optional[str] = '#e6edf3'
    kpi_cor_fundo: Optional[str] = '#161b22'
    mapa_camada: Optional[str] = 'padrao'
    chart_fonte_tamanho: Optional[int] = 12
    chart_truncar_label: Optional[bool] = False
    chart_truncar_tamanho: Optional[int] = 15
    chart_mostrar_valor: Optional[bool] = False
    testar_empresa_id: Optional[int] = None
    testar_parametros: List[dict] = []  # [{nome, valor}] em ordem — só usado no /testar
```

E no `QueryUpdate`:

```python
class QueryUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    sql_texto: Optional[str] = None
    tipo: Optional[str] = None
    cache_ttl: Optional[int] = None
    ativo: Optional[bool] = None
    kpi_cor_fonte: Optional[str] = None
    kpi_cor_fundo: Optional[str] = None
    mapa_camada: Optional[str] = None
    chart_fonte_tamanho: Optional[int] = None
    chart_truncar_label: Optional[bool] = None
    chart_truncar_tamanho: Optional[int] = None
    chart_mostrar_valor: Optional[bool] = None
```

Em `criar_query`, incluir os 4 campos no INSERT:

```python
@router.post("/")
async def criar_query(body: QueryInput, user=Depends(require_admin)):
    try:
        if body.tipo not in TIPOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {TIPOS_VALIDOS}")
        if body.mapa_camada not in CAMADAS_MAPA_VALIDAS:
            raise HTTPException(status_code=400, detail=f"Camada de mapa inválida. Use: {CAMADAS_MAPA_VALIDAS}")
        validar_sql(body.sql_texto)

        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo,
            body.kpi_cor_fonte, body.kpi_cor_fundo, body.mapa_camada,
            body.chart_fonte_tamanho, body.chart_truncar_label,
            body.chart_truncar_tamanho, body.chart_mostrar_valor)
        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar query: {e}")
```

Em `atualizar_query`, adicionar os 4 campos a `ALLOWED_COLS`:

```python
ALLOWED_COLS = {
    'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo',
    'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada',
    'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor'
}
```

(o resto de `atualizar_query` não muda — o loop genérico `for i, (k, v) in enumerate(updates.items(), ...)` já monta o UPDATE dinamicamente a partir de `ALLOWED_COLS`)

- [ ] **Step 4: Reiniciar o backend e rodar os testes novamente**

```bash
docker restart datahub_backend
docker exec datahub_backend python -m pytest tests/test_queries_chart_config.py -v
```

Expected: os 3 testes passam.

- [ ] **Step 5: Rodar a suíte completa**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```

Expected: todos os testes passam (incluindo `test_auth_tema.py` e `test_queries_mapa_camada.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_queries_chart_config.py
git commit -m "feat: add chart config fields to queries CRUD"
```

---

## Task 3: Backend — propagar config de gráfico em `renderizar_painel`

**Files:**
- Modify: `backend/routes/paineis.py`

**Interfaces:**
- Consumes: colunas `queries.chart_fonte_tamanho`, `chart_truncar_label`, `chart_truncar_tamanho`, `chart_mostrar_valor` (Task 1)
- Produces: cada indicador retornado por `GET /api/paineis/{id}/renderizar` inclui os 4 campos — consumido pelo Task 7.

- [ ] **Step 1: Editar o SELECT de `renderizar_painel`**

```python
    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
```

- [ ] **Step 2: Reiniciar o backend**

```bash
docker restart datahub_backend
```

- [ ] **Step 3: Verificar manualmente com curl**

Usar o mesmo fluxo de login já documentado no plano da feature de mapa (login → selecionar-empresa → GET renderizar), contra o painel seed `id=1` (empresa `alpha`), e confirmar que a resposta inclui `"chart_fonte_tamanho": 12` em pelo menos um indicador (default aplicado a toda linha de `queries`, igual ao `mapa_camada`).

- [ ] **Step 4: Commit**

```bash
git add backend/routes/paineis.py
git commit -m "feat: include chart config fields in renderizar_painel response"
```

---

## Task 4: Frontend — bloco de config de gráfico em `nova/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`

**Interfaces:**
- Consumes: `form.tipo`
- Produces: quando `tipo` é um dos 4 tipos de gráfico, `form.chart_*` fica disponível e é enviado a `api.criarQuery(form)` (o form inteiro já é o payload nesta tela).

- [ ] **Step 1: Adicionar os 4 campos ao estado inicial do form**

```javascript
let form = {
  slug: '', nome: '', descricao: '',
  sql_texto: '', tipo: 'kpi',
  empresa_id: null, cache_ttl: 300, ativo: true,
  kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
  mapa_camada: 'padrao',
  chart_fonte_tamanho: 12, chart_truncar_label: false,
  chart_truncar_tamanho: 15, chart_mostrar_valor: false
};
```

- [ ] **Step 2: Adicionar o bloco condicional, logo após o bloco `{#if form.tipo === 'map'}`**

```svelte
{#if ['chart_bar', 'chart_bar_horizontal', 'chart_line', 'chart_doughnut'].includes(form.tipo)}
  <div class="section-block">
    <span class="section-title">Configurações do Gráfico</span>
    <div class="cores-row">
      <label class="lbl">
        Tamanho da fonte (px)
        <input type="number" bind:value={form.chart_fonte_tamanho} min="8" max="32" style="width:90px" />
      </label>
      <label class="check-inline">
        <input type="checkbox" bind:checked={form.chart_truncar_label} />
        Truncar rótulos
      </label>
      {#if form.chart_truncar_label}
        <label class="lbl">
          Caracteres
          <input type="number" bind:value={form.chart_truncar_tamanho} min="3" max="60" style="width:90px" />
        </label>
      {/if}
      <label class="check-inline">
        <input type="checkbox" bind:checked={form.chart_mostrar_valor} />
        Mostrar valor no gráfico
      </label>
    </div>
  </div>
{/if}
```

- [ ] **Step 3: Adicionar a classe `.check-inline` ao `<style>`**

```css
.check-inline { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--text); cursor:pointer; text-transform:none; letter-spacing:0; font-weight:400; }
```

- [ ] **Step 4: Reiniciar o frontend e verificar no formulário**

```bash
docker restart datahub_frontend
```

Abrir `http://localhost:3000/configuracoes/queries/nova`, selecionar Tipo `chart_bar` — deve aparecer o bloco "Configurações do Gráfico". Marcar "Truncar rótulos" — o input "Caracteres" deve aparecer. Trocar Tipo pra `kpi` — o bloco de gráfico some, aparece o de KPI.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/nova/+page.svelte
git commit -m "feat: add chart config block to new query form"
```

---

## Task 5: Frontend — bloco de config de gráfico em `[id]/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`

**Interfaces:**
- Consumes: `q.chart_fonte_tamanho`, `q.chart_truncar_label`, `q.chart_truncar_tamanho`, `q.chart_mostrar_valor` de `GET /api/queries/{id}` (Task 2)
- Produces: `PATCH /api/queries/{id}` inclui os 4 campos no payload quando o usuário salva.

- [ ] **Step 1: Adicionar os 4 campos ao estado inicial do form**

```javascript
let form = {
  slug: '', nome: '', descricao: '',
  sql_texto: '', tipo: 'kpi',
  empresa_id: null, cache_ttl: 300, ativo: true,
  kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
  mapa_camada: 'padrao',
  chart_fonte_tamanho: 12, chart_truncar_label: false,
  chart_truncar_tamanho: 15, chart_mostrar_valor: false
};
```

- [ ] **Step 2: Carregar os valores no `onMount`**

```javascript
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
};
```

- [ ] **Step 3: Adicionar o mesmo bloco condicional do Task 4, logo após o bloco `{#if form.tipo === 'map'}`**

```svelte
{#if ['chart_bar', 'chart_bar_horizontal', 'chart_line', 'chart_doughnut'].includes(form.tipo)}
  <div class="section-block">
    <span class="section-title">Configurações do Gráfico</span>
    <div class="cores-row">
      <label class="lbl">
        Tamanho da fonte (px)
        <input type="number" bind:value={form.chart_fonte_tamanho} min="8" max="32" style="width:90px" />
      </label>
      <label class="check-inline">
        <input type="checkbox" bind:checked={form.chart_truncar_label} />
        Truncar rótulos
      </label>
      {#if form.chart_truncar_label}
        <label class="lbl">
          Caracteres
          <input type="number" bind:value={form.chart_truncar_tamanho} min="3" max="60" style="width:90px" />
        </label>
      {/if}
      <label class="check-inline">
        <input type="checkbox" bind:checked={form.chart_mostrar_valor} />
        Mostrar valor no gráfico
      </label>
    </div>
  </div>
{/if}
```

- [ ] **Step 4: Adicionar a classe `.check-inline` ao `<style>`** (idêntica ao Task 4, este arquivo tem seu próprio bloco `<style>`)

```css
.check-inline { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--text); cursor:pointer; text-transform:none; letter-spacing:0; font-weight:400; }
```

- [ ] **Step 5: Incluir os 4 campos no payload de `salvar()`**

```javascript
async function salvar() {
  erro = null;
  salvando = true;
  try {
    await api.atualizarQuery(id, {
      nome:          form.nome,
      descricao:     form.descricao,
      sql_texto:     form.sql_texto,
      tipo:          form.tipo,
      cache_ttl:     form.cache_ttl,
      ativo:         form.ativo,
      kpi_cor_fonte: form.kpi_cor_fonte,
      kpi_cor_fundo: form.kpi_cor_fundo,
      mapa_camada:   form.mapa_camada,
      chart_fonte_tamanho:   form.chart_fonte_tamanho,
      chart_truncar_label:   form.chart_truncar_label,
      chart_truncar_tamanho: form.chart_truncar_tamanho,
      chart_mostrar_valor:   form.chart_mostrar_valor,
    });
    await api.salvarParametrosQuery(id, params.map(({ _testar_valor, ...p }) => p));
    goto('/configuracoes/queries');
  } catch (e) {
    erro = e.message;
  } finally {
    salvando = false;
  }
}
```

- [ ] **Step 6: Reiniciar o frontend e verificar**

```bash
docker restart datahub_frontend
```

Editar uma query tipo `chart_bar` existente, mudar fonte pra 20, marcar truncar com 8 caracteres, marcar mostrar valor, salvar, recarregar a página — os 3 valores devem persistir e aparecer preenchidos ao reabrir.

- [ ] **Step 7: Commit**

```bash
git add "frontend/src/routes/configuracoes/queries/[id]/+page.svelte"
git commit -m "feat: persist chart config on query edit form"
```

---

## Task 6: `ChartPanel.svelte` — multi-série, truncamento, fonte, mostrar valor

**Files:**
- Modify: `frontend/src/lib/components/ChartPanel.svelte`

**Interfaces:**
- Consumes: novas props `fonteTamanho = 12`, `truncarLabel = false`, `truncarTamanho = 15`, `mostrarValor = false`; `dados` (array de objetos, cada um com `label` + `valor` + opcionalmente outras colunas numéricas)
- Produces: gráfico com N séries (N = 1 + colunas numéricas extras além de `label`/`valor`, para `chart_bar`/`chart_bar_horizontal`/`chart_line`; sempre 1 série pra `chart_doughnut`), rótulos truncados/com fonte customizada, valores exibidos quando `mostrarValor` é true.

- [ ] **Step 1: Substituir o conteúdo do arquivo**

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';
  import { usuario } from '$lib/stores/auth.js';

  export let tipo = 'bar';
  export let dados = [];
  export let fonteTamanho = 12;
  export let truncarLabel = false;
  export let truncarTamanho = 15;
  export let mostrarValor = false;

  let container;
  let chart;

  const COLORS = ['#79c0ff','#f78166','#56d364','#d2a8ff','#ffa657','#39d353'];

  function corVar(nome) {
    return getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  }

  function truncar(texto) {
    const s = String(texto ?? '');
    if (!truncarLabel || s.length <= truncarTamanho) return s;
    return s.slice(0, truncarTamanho) + '…';
  }

  // Colunas de série: todas as chaves de dados[0] exceto 'label', que tenham valor numérico
  // em pelo menos uma linha. 'valor' sempre entra primeiro (compatibilidade com queries existentes).
  function colunasSerie(dados, multiSerie) {
    if (!dados.length) return ['valor'];
    const chaves = Object.keys(dados[0]).filter(k => k !== 'label');
    const numericas = chaves.filter(k => dados.some(d => d[k] !== null && d[k] !== '' && !isNaN(Number(d[k]))));
    if (!multiSerie) return numericas.includes('valor') ? ['valor'] : numericas.slice(0, 1);
    // 'valor' primeiro, resto na ordem em que aparecem
    const resto = numericas.filter(k => k !== 'valor');
    return numericas.includes('valor') ? ['valor', ...resto] : numericas;
  }

  function buildOption(tipo, dados) {
    const labels = dados.map(d => d.label);
    const corTexto = corVar('--text');
    const corMuted = corVar('--muted');
    const corBorda = corVar('--border');

    if (tipo === 'chart_doughnut') {
      const [colValor] = colunasSerie(dados, false);
      return {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: {
          orient: 'vertical', right: 10, textStyle: { color: corTexto, fontSize: fonteTamanho },
          formatter: (nome) => truncar(nome),
        },
        series: [{
          type: 'pie', radius: ['45%', '70%'],
          data: dados.map((d, i) => ({ value: Number(d[colValor]), name: d.label, itemStyle: { color: COLORS[i % COLORS.length] } })),
          label: {
            color: corTexto, fontSize: fonteTamanho,
            formatter: (params) => mostrarValor ? `${truncar(params.name)}: ${params.value}` : truncar(params.name),
          }
        }]
      };
    }

    const isHorizontal = tipo === 'chart_bar_horizontal';
    const cols = colunasSerie(dados, tipo === 'chart_bar' || tipo === 'chart_bar_horizontal' || tipo === 'chart_line');
    const multiSerie = cols.length > 1;

    const eixoCategoria = {
      type: 'category', data: labels,
      axisLabel: { color: corMuted, fontSize: fonteTamanho, interval: 0, formatter: truncar },
    };
    const eixoValor = {
      type: 'value', axisLabel: { color: corMuted, fontSize: fonteTamanho },
      splitLine: { lineStyle: { color: corBorda } },
    };

    const series = cols.map((col, i) => ({
      type: tipo === 'chart_line' ? 'line' : 'bar',
      name: col,
      data: dados.map(d => Number(d[col])),
      smooth: tipo === 'chart_line',
      itemStyle: { color: COLORS[i % COLORS.length] },
      areaStyle: tipo === 'chart_line' ? { color: COLORS[i % COLORS.length] + '1a' } : undefined,
      barMaxWidth: 40,
      label: {
        show: mostrarValor, position: isHorizontal ? 'right' : 'top',
        color: corTexto, fontSize: fonteTamanho,
      },
    }));

    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: multiSerie ? { data: cols, top: 0, textStyle: { color: corTexto, fontSize: fonteTamanho } } : undefined,
      grid: { left: 60, right: 20, top: multiSerie ? 40 : 20, bottom: 40 },
      xAxis: isHorizontal ? eixoValor : eixoCategoria,
      yAxis: isHorizontal ? eixoCategoria : eixoValor,
      series,
    };
  }

  onMount(() => {
    chart = echarts.init(container, null, { renderer: 'svg' });
    if (dados.length) chart.setOption(buildOption(tipo, dados));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(container);
    return () => ro.disconnect();
  });

  $: if (chart && dados.length) {
    $usuario?.tema; // dependência reativa: recria a option quando o tema muda
    chart.setOption(buildOption(tipo, dados), true);
  }

  onDestroy(() => chart?.dispose());
</script>

<div bind:this={container} style="width:100%;height:260px;"></div>
```

- [ ] **Step 2: Reiniciar o frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Verificação isolada — confirmar que builda sem erro**

```bash
docker logs datahub_frontend --tail 30
```

Expected: sem erro de compilação Svelte. A verificação visual completa (gráfico real com múltiplas séries, truncamento, fonte, mostrar valor) acontece no Task 7, quando as props já estiverem conectadas ponta a ponta via painel.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/ChartPanel.svelte
git commit -m "feat: add multi-series, label truncation, font size and value display to ChartPanel"
```

---

## Task 7: Painel — propagar config de gráfico e verificação end-to-end

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `ind.chart_fonte_tamanho`, `ind.chart_truncar_label`, `ind.chart_truncar_tamanho`, `ind.chart_mostrar_valor` (Task 3), props de `ChartPanel` (Task 6)
- Produces: painel renderiza gráficos já com a configuração da query.

- [ ] **Step 1: Passar as props novas**

```svelte
{:else if ind.query_tipo?.startsWith('chart_')}
  <ChartPanel
    tipo={ind.query_tipo}
    dados={ind.dados}
    fonteTamanho={ind.chart_fonte_tamanho}
    truncarLabel={ind.chart_truncar_label}
    truncarTamanho={ind.chart_truncar_tamanho}
    mostrarValor={ind.chart_mostrar_valor}
  />
```

- [ ] **Step 2: Reiniciar o frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Teste end-to-end manual completo**

1. Criar uma query `chart_bar` com SQL de múltiplas séries:
   ```sql
   SELECT 'Fazenda A' AS label, 120 AS valor, 45 AS media_pendencia
   UNION ALL SELECT 'Fazenda B', 200, 30
   UNION ALL SELECT 'Fazenda C com Nome Bem Longo Pra Testar Truncamento', 80, 60
   ```
   Marcar "Mostrar valor no gráfico", truncar em 12 caracteres, fonte 14.
2. Adicionar a um painel, abrir — confirmar: 2 barras por fazenda (valor + media_pendencia), legenda mostrando os 2 nomes, rótulo "Fazenda C com..." truncado em 12 caracteres, todos os 3 rótulos visíveis (nenhum pulado), números aparecendo em cima das barras.
3. Testar com `chart_bar_horizontal` e `chart_line` usando a mesma query — confirmar comportamento equivalente (barras/linhas agrupadas, truncamento no eixo correspondente).
4. Testar com `chart_doughnut` na mesma query — confirmar que só usa `valor` (ignora `media_pendencia`), e que "Mostrar valor" alterna entre `Fazenda A` e `Fazenda A: 120` no rótulo da fatia.
5. Editar a query removendo "Mostrar valor" e desmarcando truncar — confirmar que volta ao comportamento sem esses efeitos.
6. Confirmar que uma query `chart_bar` antiga (só `label`+`valor`, sem configuração) continua renderizando exatamente como antes (1 série, sem legenda, fonte/tamanho default).

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: pass chart config props to ChartPanel in painel view"
```

---

## Verificação Final

- [ ] 4 colunas novas existem em `queries` (dev) e nos dois scripts de schema
- [ ] `POST`/`PATCH /api/queries` persistem os 4 campos de config de gráfico
- [ ] `pytest tests/` passa por completo
- [ ] `renderizar_painel` inclui os 4 campos em cada indicador
- [ ] Telas de cadastro/edição mostram o bloco de config só para os 4 tipos de gráfico
- [ ] Query com colunas extras de valor renderiza múltiplas séries automaticamente (bar/bar_horizontal/line)
- [ ] `chart_doughnut` ignora colunas extras, usa só `valor`
- [ ] Truncamento + fonte + mostrar valor funcionam nos 4 tipos
- [ ] `axisLabel.interval: 0` garante que nenhum rótulo é pulado
- [ ] Query de gráfico antiga (sem config, só label+valor) sem regressão visual
