# Camada de Mapa (Padrão / Satélite) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que uma query do tipo `map` tenha uma camada padrão de satélite (Esri World Imagery) configurável no cadastro, além de um botão no próprio `MapPanel` para alternar entre padrão e satélite em tempo de visualização.

**Architecture:** Nova coluna `mapa_camada` na tabela `queries` (default `'padrao'`), exposta no CRUD de `backend/routes/queries.py` e propagada por `renderizar_painel` (`backend/routes/paineis.py`). No frontend, os formulários de cadastro/edição de query ganham um seletor condicional (mesmo padrão do bloco "Cores do KPI"), e `MapPanel.svelte` ganha um terceiro tile source (satélite) mais um botão de alternância local, sem persistir a escolha feita ali.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, Leaflet, PostgreSQL (asyncpg), pytest

## Global Constraints

- JS puro — sem TypeScript
- Svelte 5 compatible — arquivos existentes usam `$:`, manter o padrão já usado nesses arquivos
- Contrato SQL do tipo `map` já existente não muda: `lat`, `lng`, `valor`, `label`
- `mapa_camada` aceita apenas `'padrao'` ou `'satelite'` — qualquer outro valor deve ser rejeitado com 400
- Tile satélite: Esri World Imagery, sem API key, imagem pura (sem rótulos sobrepostos)
- Backend roda em Docker: `datahub_backend`, `datahub_postgres` (banco `datahub_meta`, usuário `postgres`); frontend: `datahub_frontend`
- Após editar `.svelte` ou `.py`: `docker restart datahub_backend datahub_frontend`
- Sem sistema de migrations — mudanças de schema em `queries` são aplicadas via `ALTER TABLE` manual no container e refletidas em `scripts/init-db.sql` (seed dev) e `scripts/init-meta-prod.sql` (schema de produção)

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `scripts/init-db.sql` | Modificar | Adicionar `mapa_camada` na definição de `CREATE TABLE queries` (seed dev) |
| `scripts/init-meta-prod.sql` | Modificar | Adicionar `mapa_camada` na definição de `CREATE TABLE queries` (schema prod) |
| `backend/routes/queries.py` | Modificar | Campo `mapa_camada` em `QueryInput`/`QueryUpdate`, validação, INSERT, `ALLOWED_COLS` |
| `backend/tests/test_queries_mapa_camada.py` | Criar | Testes de contrato/validação do campo `mapa_camada` |
| `backend/routes/paineis.py` | Modificar | Incluir `q.mapa_camada` no SELECT de `renderizar_painel` |
| `frontend/src/routes/configuracoes/queries/nova/+page.svelte` | Modificar | Campo `mapa_camada` no form + seletor condicional quando `tipo === 'map'` |
| `frontend/src/routes/configuracoes/queries/[id]/+page.svelte` | Modificar | Idem + incluir no payload do PATCH |
| `frontend/src/lib/components/MapPanel.svelte` | Modificar | Tile satélite (Esri) + botão de alternância local |
| `frontend/src/routes/painel/[slug]/+page.svelte` | Modificar | Passar `camada={ind.mapa_camada}` para `MapPanel` |

---

## Task 1: Schema — coluna `mapa_camada` na tabela `queries`

**Files:**
- Modify: `scripts/init-db.sql:73-86`
- Modify: `scripts/init-meta-prod.sql:58-73`

**Interfaces:**
- Produces: coluna `queries.mapa_camada` (`VARCHAR(20) DEFAULT 'padrao'`), existente no Postgres de dev e refletida nos dois scripts de schema — base para os Tasks 2 e 3.

- [ ] **Step 1: Aplicar `ALTER TABLE` no Postgres de dev**

```bash
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE queries ADD COLUMN mapa_camada VARCHAR(20) DEFAULT 'padrao';"
```

Expected: `ALTER TABLE`

- [ ] **Step 2: Verificar a coluna e o backfill do default**

```bash
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "SELECT slug, tipo, mapa_camada FROM queries LIMIT 5;"
```

Expected: todas as linhas (inclusive as já existentes, tipo `kpi`/`chart_*`/`table`) mostram `mapa_camada = padrao`.

- [ ] **Step 3: Atualizar `scripts/init-db.sql`**

```sql
-- scripts/init-db.sql — dentro de CREATE TABLE queries (linha ~73-86)
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
    UNIQUE (slug, empresa_id)
);
```

- [ ] **Step 4: Atualizar `scripts/init-meta-prod.sql`**

```sql
-- scripts/init-meta-prod.sql — dentro de CREATE TABLE queries (linha ~58-73)
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
    UNIQUE (slug, empresa_id)
);
CREATE INDEX idx_queries_empresa ON queries(empresa_id);
CREATE INDEX idx_queries_slug ON queries(slug);
```

- [ ] **Step 5: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql
git commit -m "feat: add mapa_camada column to queries table"
```

**Nota para deploy:** este mesmo `ALTER TABLE` (Step 1) precisa rodar manualmente no Postgres de produção (VPS) quando o deploy avançar — não é feito por este plano.

---

## Task 2: Backend — campo `mapa_camada` no CRUD de queries

**Files:**
- Modify: `backend/routes/queries.py:11-51` (models e `TIPOS_VALIDOS`)
- Modify: `backend/routes/queries.py:196-217` (`criar_query`)
- Modify: `backend/routes/queries.py:219-262` (`atualizar_query`)
- Test: `backend/tests/test_queries_mapa_camada.py`

**Interfaces:**
- Consumes: fixtures `client` e `auth_token` de `backend/tests/conftest.py` (login admin em `alpha`)
- Produces: `POST /api/queries/` e `PATCH /api/queries/{id}` aceitam/validam `mapa_camada` (`'padrao'` ou `'satelite'`); resposta inclui `mapa_camada` no dict retornado — usado pelo frontend nos Tasks 4 e 5.

- [ ] **Step 1: Escrever os testes (devem falhar — campo ainda não existe)**

Criar `backend/tests/test_queries_mapa_camada.py`:

```python
MAP_SQL = "SELECT -23.5 AS lat, -46.6 AS lng, 100 AS valor, 'SP' AS label"


def _criar_query_map(client, auth_token, slug, mapa_camada=None):
    body = {
        "slug": slug,
        "nome": "Teste Mapa Camada",
        "sql_texto": MAP_SQL,
        "tipo": "map",
    }
    if mapa_camada is not None:
        body["mapa_camada"] = mapa_camada
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_usa_padrao_por_default(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_default")
    assert res.status_code == 200
    body = res.json()
    assert body["mapa_camada"] == "padrao"
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_com_satelite(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_satelite", mapa_camada="satelite")
    assert res.status_code == 200
    body = res.json()
    assert body["mapa_camada"] == "satelite"
    client.delete(
        f"/api/queries/{body['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_map_com_camada_invalida(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_invalida", mapa_camada="rua")
    assert res.status_code == 400


def test_atualizar_query_mapa_camada(client, auth_token):
    res = _criar_query_map(client, auth_token, "teste_mapa_camada_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"mapa_camada": "satelite"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["mapa_camada"] == "satelite"

    invalid_res = client.patch(
        f"/api/queries/{query_id}",
        json={"mapa_camada": "rua"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert invalid_res.status_code == 400

    client.delete(
        f"/api/queries/{query_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
docker exec datahub_backend python -m pytest tests/test_queries_mapa_camada.py -v
```

Expected: 3 de 4 falham.
- `test_criar_query_map_usa_padrao_por_default` **passa mesmo sem a Step 3** — a coluna já tem default `'padrao'` no Postgres (Task 1), e `RETURNING *` já devolve isso independente do código Python. Esse teste serve de regressão, não prova a mudança desta task.
- `test_criar_query_map_com_satelite` falha: `body.mapa_camada` é ignorado pelo Pydantic (campo não existe no model) e pelo INSERT (coluna não listada), então a query é salva com `'padrao'` em vez de `'satelite'` — o assert compara `'padrao' == 'satelite'` e falha.
- `test_criar_query_map_com_camada_invalida` falha: sem validação, o POST aceita o valor `'rua'` (que é ignorado) e retorna 200 em vez do 400 esperado.
- `test_atualizar_query_mapa_camada` falha: `'mapa_camada'` ainda não está em `ALLOWED_COLS`, então o PATCH retorna 400 "Campo inválido: mapa_camada" onde o teste esperava 200.

- [ ] **Step 3: Implementar em `backend/routes/queries.py`**

Adicionar constante e ajustar os models (linhas ~11-51):

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
    testar_empresa_id: Optional[int] = None
    testar_parametros: List[dict] = []  # [{nome, valor}] em ordem — só usado no /testar


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
```

```python
TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map'
}

CAMADAS_MAPA_VALIDAS = {'padrao', 'satelite'}
```

Em `criar_query` (linhas ~196-217), validar e incluir no INSERT:

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
            INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo, kpi_cor_fonte, kpi_cor_fundo, mapa_camada)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo,
            body.kpi_cor_fonte, body.kpi_cor_fundo, body.mapa_camada)
        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar query: {e}")
```

Em `atualizar_query` (linhas ~219-262), adicionar `'mapa_camada'` a `ALLOWED_COLS` e validar o valor quando presente:

```python
@router.patch("/{query_id}")
async def atualizar_query(query_id: int, body: QueryUpdate, user=Depends(require_admin)):
    try:
        atual = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
        if not atual:
            raise HTTPException(status_code=404, detail="Query não encontrada")

        atual = dict(atual[0])
        updates = body.dict(exclude_none=True)

        if not updates:
            return atual

        ALLOWED_COLS = {'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo', 'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada'}
        for k in updates:
            if k not in ALLOWED_COLS:
                raise HTTPException(status_code=400, detail=f"Campo inválido: {k}")

        if "mapa_camada" in updates and updates["mapa_camada"] not in CAMADAS_MAPA_VALIDAS:
            raise HTTPException(status_code=400, detail=f"Camada de mapa inválida. Use: {CAMADAS_MAPA_VALIDAS}")

        if "sql_texto" in updates:
            validar_sql(updates["sql_texto"])

        campos = []
        valores = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            campos.append(f"{k} = ${i}")
            valores.append(v)

        valores.append(query_id)
        sql = f"UPDATE queries SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
        rows = await query_meta(sql, *valores)

        if atual.get("empresa_id"):
            emp = await query_meta("SELECT slug FROM empresas WHERE id = $1", atual["empresa_id"])
            if emp:
                await invalidar_cache_empresa(emp[0]["slug"])

        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar query: {e}")
```

- [ ] **Step 4: Reiniciar o backend e rodar os testes novamente**

```bash
docker restart datahub_backend
docker exec datahub_backend python -m pytest tests/test_queries_mapa_camada.py -v
```

Expected: os 4 testes passam.

- [ ] **Step 5: Rodar a suíte completa pra garantir que nada quebrou**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```

Expected: todos os testes passam (incluindo `test_auth_tema.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_queries_mapa_camada.py
git commit -m "feat: add mapa_camada field with validation to queries CRUD"
```

---

## Task 3: Backend — propagar `mapa_camada` em `renderizar_painel`

**Files:**
- Modify: `backend/routes/paineis.py:293-299`

**Interfaces:**
- Consumes: coluna `queries.mapa_camada` (Task 1)
- Produces: cada indicador retornado por `GET /api/paineis/{id}/renderizar` inclui `mapa_camada` — consumido pelo frontend no Task 7.

- [ ] **Step 1: Editar o SELECT de `renderizar_painel`**

```python
# backend/routes/paineis.py — linha ~293-299
    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada
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

O painel seed `id=1` (empresa `alpha`) já tem indicadores e o usuário admin (`id=1`) já tem acesso (`painel_usuarios`). Como `mapa_camada` tem default `'padrao'` para toda linha de `queries` (Task 1), isso já é suficiente pra verificar que o JOIN traz o campo:

```bash
TOKEN=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['session_token'])")

EMPRESA_ID=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123"}' | python -c "import sys,json; d=json.load(sys.stdin); print(next(e['id'] for e in d['empresas'] if e['slug']=='alpha'))")

JWT=$(curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa \
  -H "Content-Type: application/json" \
  -d "{\"session_token\":\"$TOKEN\",\"empresa_id\":$EMPRESA_ID}" | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s http://localhost:3001/api/paineis/1/renderizar -H "Authorization: Bearer $JWT" | python -m json.tool | grep -A1 mapa_camada
```

Expected: pelo menos uma ocorrência de `"mapa_camada": "padrao"` na saída (um por indicador do painel 1).

- [ ] **Step 4: Commit**

```bash
git add backend/routes/paineis.py
git commit -m "feat: include mapa_camada in renderizar_painel response"
```

---

## Task 4: Frontend — seletor de camada em `nova/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte:7-12` (form)
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte:152-176` (bloco condicional, logo após o bloco de cores do KPI)

**Interfaces:**
- Consumes: `form.tipo` (já existente)
- Produces: quando `tipo === 'map'`, `form.mapa_camada` fica disponível e é enviado a `api.criarQuery(form)` (o form inteiro já é o payload nesta tela — nenhuma mudança extra na chamada é necessária).

- [ ] **Step 1: Adicionar `mapa_camada` ao estado inicial do form**

```javascript
// frontend/src/routes/configuracoes/queries/nova/+page.svelte — linha ~7-12
let form = {
  slug: '', nome: '', descricao: '',
  sql_texto: '', tipo: 'kpi',
  empresa_id: null, cache_ttl: 300, ativo: true,
  kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
  mapa_camada: 'padrao'
};
```

- [ ] **Step 2: Adicionar o bloco condicional logo após o bloco `{#if form.tipo === 'kpi'}`**

```svelte
{#if form.tipo === 'map'}
  <div class="section-block">
    <span class="section-title">Camada do Mapa</span>
    <label class="lbl">
      Camada padrão
      <select bind:value={form.mapa_camada}>
        <option value="padrao">Padrão (tema claro/escuro)</option>
        <option value="satelite">Satélite</option>
      </select>
    </label>
  </div>
{/if}
```

- [ ] **Step 3: Reiniciar o frontend e verificar no formulário**

```bash
docker restart datahub_frontend
```

Abrir `http://localhost:3000/configuracoes/queries/nova`, selecionar Tipo `map` — deve aparecer o bloco "Camada do Mapa" com o select mostrando "Padrão (tema claro/escuro)" selecionado por padrão. Trocar Tipo pra `kpi` — o bloco de mapa deve sumir e o de "Cores do KPI" aparecer (comportamento mutuamente exclusivo, sem alteração de código extra pois são blocos `{#if}` independentes).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/nova/+page.svelte
git commit -m "feat: add map layer selector to new query form"
```

---

## Task 5: Frontend — seletor de camada em `[id]/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:10-15` (form)
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:44-55` (onMount)
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:117-138` (salvar)
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:189-213` (bloco condicional)

**Interfaces:**
- Consumes: `q.mapa_camada` retornado por `GET /api/queries/{id}` (Task 2)
- Produces: `PATCH /api/queries/{id}` inclui `mapa_camada` no payload quando o usuário salva.

- [ ] **Step 1: Adicionar `mapa_camada` ao estado inicial do form**

```javascript
// frontend/src/routes/configuracoes/queries/[id]/+page.svelte — linha ~10-15
let form = {
  slug: '', nome: '', descricao: '',
  sql_texto: '', tipo: 'kpi',
  empresa_id: null, cache_ttl: 300, ativo: true,
  kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
  mapa_camada: 'padrao'
};
```

- [ ] **Step 2: Carregar o valor no `onMount`**

```javascript
// frontend/src/routes/configuracoes/queries/[id]/+page.svelte — dentro de onMount, linha ~44-55
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
};
```

- [ ] **Step 3: Adicionar o bloco condicional logo após o bloco `{#if form.tipo === 'kpi'}`**

```svelte
{#if form.tipo === 'map'}
  <div class="section-block">
    <span class="section-title">Camada do Mapa</span>
    <label class="lbl">
      Camada padrão
      <select bind:value={form.mapa_camada}>
        <option value="padrao">Padrão (tema claro/escuro)</option>
        <option value="satelite">Satélite</option>
      </select>
    </label>
  </div>
{/if}
```

- [ ] **Step 4: Incluir `mapa_camada` no payload de `salvar()`**

```javascript
// frontend/src/routes/configuracoes/queries/[id]/+page.svelte — dentro de salvar(), linha ~117-138
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

- [ ] **Step 5: Reiniciar o frontend e verificar**

```bash
docker restart datahub_frontend
```

Abrir a edição de uma query tipo `map` existente (ou criar uma na tela `nova` primeiro), trocar a camada pra "Satélite", salvar, recarregar a página — o select deve continuar mostrando "Satélite" (confirma que persistiu e foi recarregado corretamente).

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/routes/configuracoes/queries/[id]/+page.svelte"
git commit -m "feat: persist map layer selection on query edit form"
```

---

## Task 6: `MapPanel.svelte` — tile satélite e botão de alternância

**Files:**
- Modify: `frontend/src/lib/components/MapPanel.svelte` (arquivo inteiro, 68 linhas)

**Interfaces:**
- Consumes: nova prop `camada` (default `'padrao'`)
- Produces: o mapa renderiza com Esri World Imagery quando a camada ativa é `'satelite'` (seja pela prop inicial, seja pelo botão de alternância); marcadores e `fitBounds` continuam funcionando sem alteração de comportamento.

- [ ] **Step 1: Substituir o conteúdo do arquivo**

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import { usuario } from '$lib/stores/auth.js';

  export let pontos = [];
  export let camada = 'padrao';

  let container;
  let map;
  let markers = [];
  let leafletRef = null;
  let tileLayer = null;
  let temaAtual = null;
  let camadaAtiva = camada;

  const TILE_URLS = {
    escuro:   'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    claro:    'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    satelite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  };
  const MARKER_STROKE = { escuro: '#0d1117', claro: '#ffffff' };

  onMount(async () => {
    const L = (await import('leaflet')).default;
    await import('leaflet/dist/leaflet.css');

    map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);

    leafletRef = L;
    aplicarTileLayer(L, $usuario?.tema ?? 'escuro');
    renderPontos(L);
  });

  $: if (map && leafletRef && $usuario?.tema && $usuario.tema !== temaAtual) {
    aplicarTileLayer(leafletRef, $usuario.tema);
    renderPontos(leafletRef);
  }

  $: if (map && leafletRef && pontos) renderPontos(leafletRef);

  function aplicarTileLayer(L, tema) {
    if (tileLayer) tileLayer.remove();
    const url = camadaAtiva === 'satelite' ? TILE_URLS.satelite : (TILE_URLS[tema] ?? TILE_URLS.escuro);
    tileLayer = L.tileLayer(url, { maxZoom: 19 }).addTo(map);
    temaAtual = tema;
  }

  function alternarCamada() {
    camadaAtiva = camadaAtiva === 'satelite' ? 'padrao' : 'satelite';
    aplicarTileLayer(leafletRef, $usuario?.tema ?? 'escuro');
    renderPontos(leafletRef);
  }

  function renderPontos(L) {
    markers.forEach(m => m.remove());
    markers = [];
    if (!pontos.length) {
      map.setView([-15.8, -47.9], 4);
      return;
    }
    const corContorno = MARKER_STROKE[temaAtual] ?? MARKER_STROKE.escuro;
    const maxVal = Math.max(...pontos.map(p => Number(p.valor) || 0), 1);
    pontos.forEach(p => {
      const r = 8 + ((Number(p.valor) || 0) / maxVal) * 22;
      const m = L.circleMarker([p.lat, p.lng], {
        radius: r, fillColor: '#79c0ff', color: corContorno,
        fillOpacity: .75, weight: 1.5
      }).bindPopup(`<b>${p.label}</b><br>${p.valor}`).addTo(map);
      markers.push(m);
    });
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds(), { padding: [32, 32], maxZoom: 12 });
  }

  onDestroy(() => map?.remove());
</script>

<div class="map-wrap">
  <div bind:this={container} class="map-container"></div>
  <button class="camada-toggle" on:click={alternarCamada}>
    {camadaAtiva === 'satelite' ? 'Padrão' : 'Satélite'}
  </button>
</div>

<style>
.map-wrap { position: relative; width: 100%; height: 300px; }
.map-container { width: 100%; height: 100%; border-radius: 8px; overflow: hidden; }
.camada-toggle {
  position: absolute; top: 8px; right: 8px; z-index: 1000;
  font-size: 11px; padding: 4px 10px; border-radius: 4px;
  border: 1px solid rgba(0,0,0,.25); background: rgba(255,255,255,.9); color: #111;
  cursor: pointer; font-family: inherit;
}
.camada-toggle:hover { background: #fff; }
</style>
```

- [ ] **Step 2: Reiniciar o frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Verificação manual isolada do componente**

Como não há uma query `map` ainda ligada a um painel visível (isso acontece no Task 7), a verificação completa do satélite acontece lá. Por ora, confirmar que o frontend builda sem erro:

```bash
docker logs datahub_frontend --tail 30
```

Expected: sem erros de compilação Svelte no log após o restart.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/MapPanel.svelte
git commit -m "feat: add satellite tile layer and toggle button to MapPanel"
```

---

## Task 7: Painel — propagar `camada` e verificação end-to-end

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte:199-200`

**Interfaces:**
- Consumes: `ind.mapa_camada` (Task 3), prop `camada` de `MapPanel` (Task 6)
- Produces: painel renderiza o mapa já na camada configurada pela query, com o botão de alternância funcional.

- [ ] **Step 1: Passar a prop `camada`**

```svelte
{:else if ind.query_tipo === 'map'}
  <MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} />
```

- [ ] **Step 2: Reiniciar o frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Teste end-to-end manual completo**

1. Em `http://localhost:3000/configuracoes/queries/nova`, criar uma query:
   - Slug: `teste_mapa_satelite`, Nome: `Teste Mapa Satélite`, Tipo: `map`
   - Camada do Mapa: `Satélite`
   - SQL:
     ```sql
     SELECT -23.55 AS lat, -46.63 AS lng, 500 AS valor, 'São Paulo' AS label
     UNION ALL SELECT -22.90, -43.17, 300, 'Rio de Janeiro'
     ```
   - Testar Query → `✓ Contrato OK` → Salvar
2. Em `http://localhost:3000/configuracoes/paineis`, editar um painel existente (ou criar um novo) e adicionar `teste_mapa_satelite` como indicador.
3. Abrir o painel: o mapa deve carregar já mostrando **imagem de satélite** (não o mapa vetorial escuro/claro), com os 2 marcadores auto-ajustados (SP e RJ).
4. Clicar no botão "Padrão" no canto do mapa — as tiles devem trocar pra o mapa vetorial (escuro ou claro, conforme o tema do usuário logado), com os marcadores preservados. O botão deve passar a mostrar "Satélite".
5. Clicar novamente — deve voltar pro satélite.
6. Editar a mesma query em `/configuracoes/queries/{id}`, trocar Camada do Mapa pra "Padrão (tema claro/escuro)", salvar, recarregar o painel — deve abrir agora já em modo padrão (comportamento idêntico ao que existia antes desta feature).
7. Confirmar que um indicador `kpi` ou `chart_*` no mesmo painel continua renderizando normalmente (nenhuma regressão).

- [ ] **Step 4: Remover a query de teste**

Na tela `/configuracoes/queries`, excluir `teste_mapa_satelite` (e removê-la do painel de teste, se foi adicionada a um painel real).

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: render MapPanel with configured layer in painel view"
```

---

## Verificação Final

- [ ] Coluna `mapa_camada` existe em `queries` (dev) e nos dois scripts de schema
- [ ] `POST`/`PATCH /api/queries` validam `mapa_camada` (400 em valor inválido, default `padrao`)
- [ ] `pytest tests/` passa por completo (`docker exec datahub_backend python -m pytest tests/ -v`)
- [ ] `renderizar_painel` inclui `mapa_camada` em cada indicador
- [ ] Telas de cadastro/edição de query mostram o seletor de camada só quando `tipo === 'map'`
- [ ] Painel com query `mapa_camada = 'satelite'` abre direto em satélite
- [ ] Botão de alternância no `MapPanel` troca entre padrão e satélite sem recarregar a página
- [ ] KPI, charts e demais tipos de query — sem regressão
