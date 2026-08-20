# Filtro por clique em gráficos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ao clicar numa barra/fatia/ponto de um gráfico (`chart_bar`, `chart_bar_horizontal`, `chart_doughnut`, `chart_line`) dentro de um painel, aplicar automaticamente o filtro de uma variável já cadastrada nesse painel usando o valor daquele item clicado — reaproveitando o mesmo `filtrosAtivos` que os filtros do topo já usam.

**Architecture:** Duas colunas novas sem tabela filha: `queries.chart_filtro_coluna` (qual coluna do resultado tem o id bruto pro filtro, configurada uma vez na query) e `painel_indicadores.filtro_clique_variavel_id` (qual variável do painel esse indicador aciona ao clicar, configurada por indicador dentro do painel). `renderizar_painel` resolve a variável-alvo (slug + tipo) num JOIN extra e devolve tudo pronto pro frontend. `ChartPanel.svelte` ganha um handler de clique (via API de eventos do ECharts) que despacha o valor bruto pro componente pai; `painel/[slug]/+page.svelte` decide select (substitui) vs multiselect (alterna) olhando o tipo da variável, atualiza `filtrosAtivos` e recarrega os dados na hora.

**Tech Stack:** SvelteKit (JS puro, Svelte 5) + ECharts, FastAPI/Python, asyncpg, PostgreSQL, pytest

**Spec:** `docs/superpowers/specs/2026-08-19-filtro-clique-grafico-design.md`

## Global Constraints

- Clique só tem efeito se a variável-alvo já estiver adicionada ao painel (aba "Filtros e Acesso") — sem isso, o indicador nem mostra a opção de configurar filtro por clique.
- Valor do filtro vem de uma coluna explícita do SQL (`chart_filtro_coluna`), nunca por casamento de texto com o rótulo exibido.
- Comportamento de clique segue o `tipo` da variável-alvo: `select` substitui o valor (clicar de novo no mesmo limpa), `multiselect` alterna (toggle) — sem configuração extra de "modo".
- Filtro aplica imediatamente ao clicar (sem esperar o botão "Aplicar"); "Limpar filtros" já reseta de graça (mesmo `filtrosAtivos`/`valoresIniciais()`).
- Sem correspondência não é erro — o valor bruto vai direto pro filtro; se não bater com nada nas outras queries, elas voltam vazias (mesmo comportamento de qualquer filtro sem resultado hoje).
- A coluna de filtro não pode virar série numérica extra em gráficos multi-série — precisa ser excluída da detecção automática de séries do `ChartPanel`.
- Aplica só a `chart_bar`, `chart_bar_horizontal`, `chart_doughnut`, `chart_line`.
- Sem sistema de migrations — `ALTER TABLE` manual + refletir em `scripts/init-meta-prod.sql` e README ("Deltas de schema pendentes"). `scripts/init-db.sql` só recebe a coluna nova de `queries` (a tabela já está definida lá); `painel_indicadores` não está definida nesse script (gap pré-existente do projeto, fora de escopo desta feature).
- Frontend sem framework de testes — verificação manual via navegador (o usuário faz essa verificação, não o executor deste plano).

---

## Task 1: Schema — `queries.chart_filtro_coluna` + `painel_indicadores.filtro_clique_variavel_id`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`

**Interfaces:**
- Produces: coluna `queries.chart_filtro_coluna TEXT`; coluna `painel_indicadores.filtro_clique_variavel_id INTEGER REFERENCES variaveis(id) ON DELETE SET NULL`.

- [ ] **Step 1: Aplicar no Postgres de dev**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "
ALTER TABLE queries ADD COLUMN chart_filtro_coluna TEXT;
ALTER TABLE painel_indicadores ADD COLUMN filtro_clique_variavel_id INTEGER REFERENCES variaveis(id) ON DELETE SET NULL;
"
```

- [ ] **Step 2: Verificar que aplicou**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\d queries" | grep chart_filtro_coluna
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\d painel_indicadores" | grep filtro_clique_variavel_id
```

Expected: as duas colunas aparecem.

- [ ] **Step 3: Refletir em `scripts/init-db.sql`**

No bloco `CREATE TABLE queries` (linha 77-106), logo após `subquery_id INTEGER REFERENCES queries(id) ON DELETE SET NULL,` (linha 104) e antes de `UNIQUE (slug, empresa_id)`, adicionar:

```sql
    chart_filtro_coluna TEXT,
```

`painel_indicadores` **não está definida** em `scripts/init-db.sql` (só existe em `scripts/init-meta-prod.sql` — gap pré-existente do projeto, não desta feature). Não criar a tabela aqui; nada a fazer nesse arquivo pra essa segunda coluna.

- [ ] **Step 4: Refletir em `scripts/init-meta-prod.sql`**

No bloco `CREATE TABLE queries` (linha 62-98), logo após `kpi_imagem_mime TEXT,` (linha 96) e antes de `UNIQUE (slug, empresa_id)`, adicionar:

```sql
    chart_filtro_coluna   TEXT,
```

No bloco `CREATE TABLE painel_indicadores` (linha 165-176), logo após `posicao     INTEGER DEFAULT 0,` (linha 174) e antes de `UNIQUE (painel_id, linha, coluna)`, adicionar:

```sql
    filtro_clique_variavel_id INTEGER REFERENCES variaveis(id) ON DELETE SET NULL,
```

- [ ] **Step 5: Atualizar `README.md` — "Deltas de schema pendentes"**

No bloco de `SELECT column_name ... WHERE table_name = 'queries'` (linha ~139-141), adicionar `'chart_filtro_coluna'` à lista de colunas verificadas:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'queries'
  AND column_name IN ('pdf_orientacao', 'kpi_imagem_habilitada', 'kpi_imagem_posicao', 'kpi_imagem', 'kpi_imagem_mime', 'chart_filtro_coluna');
```

Adicionar uma nova checagem logo depois, pra `painel_indicadores`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'painel_indicadores'
  AND column_name = 'filtro_clique_variavel_id';
```

No bloco de `ALTER TABLE`s a aplicar (final da seção, depois da linha `ALTER TABLE queries ADD COLUMN kpi_imagem_mime TEXT;`), adicionar:

```sql
-- 2026-08-19 — filtro por clique em gráficos: coluna do resultado com o id bruto pro filtro,
-- e qual variável do painel esse indicador aciona ao clicar
ALTER TABLE queries ADD COLUMN chart_filtro_coluna TEXT;
ALTER TABLE painel_indicadores ADD COLUMN filtro_clique_variavel_id INTEGER REFERENCES variaveis(id) ON DELETE SET NULL;
```

- [ ] **Step 6: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md
git commit -m "feat: add schema for click-to-filter on charts"
```

---

## Task 2: Backend — `queries.py`: campo `chart_filtro_coluna`

**Files:**
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_queries_chart_filtro_coluna.py`

**Interfaces:**
- Consumes: schema do Task 1.
- Produces: `QueryInput.chart_filtro_coluna: Optional[str]`, `QueryUpdate.chart_filtro_coluna: Optional[str]` — devolvido em qualquer resposta de query (`GET`/`POST`/`PATCH`, já que todas usam `SELECT *`/`RETURNING *`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_queries_chart_filtro_coluna.py`:

```python
CHART_SQL = "SELECT 'A' AS label, 10 AS valor, 1 AS categoria_id UNION ALL SELECT 'B', 20, 2"


def _criar_query_chart(client, auth_token, slug, **overrides):
    body = {
        "slug": slug,
        "nome": "Teste Filtro Clique",
        "sql_texto": CHART_SQL,
        "tipo": "chart_bar",
        **overrides,
    }
    return client.post(
        "/api/queries/",
        json=body,
        headers={"Authorization": f"Bearer {auth_token}"},
    )


def test_criar_query_chart_sem_filtro_coluna_por_padrao(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_filtro_clique_default")
    assert res.status_code == 200
    body = res.json()
    assert body["chart_filtro_coluna"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_chart_com_filtro_coluna(client, auth_token):
    res = _criar_query_chart(
        client, auth_token, "teste_filtro_clique_custom",
        chart_filtro_coluna="categoria_id",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["chart_filtro_coluna"] == "categoria_id"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_chart_filtro_coluna(client, auth_token):
    res = _criar_query_chart(client, auth_token, "teste_filtro_clique_update")
    query_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/queries/{query_id}",
        json={"chart_filtro_coluna": "categoria_id"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["chart_filtro_coluna"] == "categoria_id"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_chart_filtro_coluna.py -v`
Expected: FAIL — `KeyError: 'chart_filtro_coluna'` (campo não existe em `QueryInput`/`QueryUpdate`, então nem chega no banco).

- [ ] **Step 3: Implement — `backend/routes/queries.py`**

Em `QueryInput` (depois de `kpi_imagem_posicao: Optional[str] = 'direita'`, linha 42):

```python
    chart_filtro_coluna: Optional[str] = None
```

Em `QueryUpdate` (depois de `kpi_imagem_posicao: Optional[str] = None`, linha 72):

```python
    chart_filtro_coluna: Optional[str] = None
```

Em `ALLOWED_COLS` dentro de `atualizar_query` (linha 437-445), adicionar `'chart_filtro_coluna'` ao conjunto:

```python
        ALLOWED_COLS = {
            'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo',
            'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada',
            'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor',
            'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna',
            'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio', 'meta_coluna_fim',
            'meta_cor_dentro', 'meta_cor_fora', 'subquery_id',
            'pdf_orientacao', 'kpi_imagem_habilitada', 'kpi_imagem_posicao',
            'chart_filtro_coluna'
        }
```

`atualizar_query` já monta o `UPDATE` dinamicamente a partir de `body.dict(exclude_none=True)` (linha 465-473) — nenhuma outra mudança necessária ali, o campo novo é coberto automaticamente assim que existe no modelo e em `ALLOWED_COLS`.

Em `criar_query`, o `INSERT` (linha 392-414) é uma lista fixa de colunas — adicionar `chart_filtro_coluna` no final da lista de colunas, do placeholder `$30` e do valor:

```python
        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor,
                chart_valor_label, impressao_habilitada, impressao_caminho, impressao_coluna,
                meta_habilitada, meta_coluna_valor, meta_coluna_inicio, meta_coluna_fim,
                meta_cor_dentro, meta_cor_fora, subquery_id,
                pdf_orientacao, kpi_imagem_habilitada, kpi_imagem_posicao,
                chart_filtro_coluna
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
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
            body.chart_filtro_coluna)
        return _com_kpi_imagem_url(dict(rows[0]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_chart_filtro_coluna.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/queries.py backend/tests/test_queries_chart_filtro_coluna.py
git commit -m "feat: add chart_filtro_coluna field to queries"
```

---

## Task 3: Backend — `paineis.py`: `filtro_clique_variavel_id` no indicador + resolução em `renderizar_painel`

**Files:**
- Modify: `backend/routes/paineis.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_paineis_filtro_clique_grafico.py`

**Interfaces:**
- Consumes: schema do Task 1, `queries.chart_filtro_coluna` do Task 2.
- Produces: `IndicadorInput.filtro_clique_variavel_id: Optional[int]`; `GET /api/paineis/{id}/renderizar` devolve, em cada indicador, `chart_filtro_coluna`, `filtro_clique_variavel_id`, `filtro_clique_variavel_slug`, `filtro_clique_variavel_tipo` (todos `null` quando não configurado).

- [ ] **Step 1: Adicionar `hard_delete_variavel` ao `conftest.py`**

`DELETE /api/variaveis/{id}` só desativa (`ativo = false`) — mesma armadilha já documentada pra painéis/usuários. Adicionar em `backend/tests/conftest.py`, depois de `hard_delete_usuario` (linha 35-44):

```python
def hard_delete_variavel(variavel_id: int):
    """Mesma lógica de hard_delete_painel, pra variáveis criadas em teste --
    DELETE /api/variaveis/{id} só desativa (ativo=false)."""
    async def _exec():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM variaveis WHERE id = $1", variavel_id)
        finally:
            await conn.close()
    asyncio.run(_exec())
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_paineis_filtro_clique_grafico.py`:

```python
import uuid
from conftest import hard_delete_painel, hard_delete_variavel


def test_renderizar_painel_anexa_filtro_clique_configurado(client, auth_token):
    var_slug = f"var_filtro_clique_{uuid.uuid4().hex[:8]}"
    variavel = client.post(
        "/api/variaveis/",
        json={
            "slug": var_slug,
            "nome": "Categoria Teste",
            "tipo": "multiselect",
            "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_filtro_clique_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Filtro Clique",
            "sql_texto": "SELECT 'A' AS label, 10 AS valor, 1 AS categoria_id",
            "tipo": "chart_bar",
            "cache_ttl": 0,
            "chart_filtro_coluna": "categoria_id",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_filtro_clique_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Filtro Clique"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]

    client.put(
        f"/api/paineis/{painel_id}/variaveis",
        json=[{"variavel_id": variavel["id"]}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    client.put(
        f"/api/paineis/{painel_id}/indicadores",
        json=[{
            "query_slug": query_slug, "linha": 1, "coluna": 1,
            "filtro_clique_variavel_id": variavel["id"],
        }],
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    try:
        res = client.get(
            f"/api/paineis/{painel_id}/renderizar",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        ind = res.json()["indicadores"][0]
        assert ind["chart_filtro_coluna"] == "categoria_id"
        assert ind["filtro_clique_variavel_id"] == variavel["id"]
        assert ind["filtro_clique_variavel_slug"] == var_slug
        assert ind["filtro_clique_variavel_tipo"] == "multiselect"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        hard_delete_variavel(variavel["id"])


def test_renderizar_painel_sem_filtro_clique_configurado_retorna_none(client, auth_token):
    query_slug = f"query_sem_filtro_clique_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Sem Filtro Clique",
            "sql_texto": "SELECT 'A' AS label, 10 AS valor",
            "tipo": "chart_bar",
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_sem_filtro_clique_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Sem Filtro Clique"},
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
        assert ind["chart_filtro_coluna"] is None
        assert ind["filtro_clique_variavel_id"] is None
        assert ind["filtro_clique_variavel_slug"] is None
        assert ind["filtro_clique_variavel_tipo"] is None
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_adicionar_indicador_com_filtro_clique_variavel_id(client, auth_token):
    var_slug = f"var_ind_filtro_{uuid.uuid4().hex[:8]}"
    variavel = client.post(
        "/api/variaveis/",
        json={
            "slug": var_slug, "nome": "Var Indicador", "tipo": "select",
            "query_fonte": "SELECT 1 AS valor, 'Um' AS label",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    query_slug = f"query_ind_filtro_{uuid.uuid4().hex[:8]}"
    query = client.post(
        "/api/queries/",
        json={
            "slug": query_slug, "nome": "Query Ind Filtro",
            "sql_texto": "SELECT 'A' AS label, 1 AS valor", "tipo": "chart_bar", "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()

    painel_slug = f"painel_ind_filtro_{uuid.uuid4().hex[:8]}"
    painel_id = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Ind Filtro"},
        headers={"Authorization": f"Bearer {auth_token}"},
    ).json()["id"]

    try:
        res = client.post(
            f"/api/paineis/{painel_id}/indicadores",
            json={
                "query_slug": query_slug, "linha": 1, "coluna": 1,
                "filtro_clique_variavel_id": variavel["id"],
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        assert res.json()["filtro_clique_variavel_id"] == variavel["id"]
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query['id']}", headers={"Authorization": f"Bearer {auth_token}"})
        hard_delete_variavel(variavel["id"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_filtro_clique_grafico.py -v`
Expected: FAIL — `filtro_clique_variavel_id` não existe em `IndicadorInput` (erro 422 nos `POST`/`PUT` de indicadores) e não aparece no retorno de `renderizar_painel`.

- [ ] **Step 4: Implement — `backend/routes/paineis.py`**

Em `IndicadorInput` (depois de `posicao: int = 0`, linha 43):

```python
    filtro_clique_variavel_id: Optional[int] = None
```

Em `adicionar_indicador` (linha 248-260), incluir a coluna no `INSERT`:

```python
@router.post("/{painel_id}/indicadores")
async def adicionar_indicador(painel_id: int, body: IndicadorInput, user=Depends(require_admin)):
    q = await query_meta("SELECT id FROM queries WHERE slug = $1", body.query_slug)
    if not q:
        raise HTTPException(404, f"Query '{body.query_slug}' não encontrada")
    rows = await query_meta("""
        INSERT INTO painel_indicadores
            (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, filtro_clique_variavel_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        RETURNING *
    """, painel_id, body.query_slug, body.titulo,
        body.linha, body.coluna, body.col_span, body.row_span, body.posicao,
        body.filtro_clique_variavel_id)
    return dict(rows[0])
```

Em `salvar_indicadores` (linha 263-278), incluir a coluna no `INSERT`:

```python
@router.put("/{painel_id}/indicadores")
async def salvar_indicadores(
    painel_id: int, indicadores: List[IndicadorInput], user=Depends(require_admin)
):
    await query_meta("DELETE FROM painel_indicadores WHERE painel_id = $1", painel_id)
    resultado = []
    for ind in indicadores:
        rows = await query_meta("""
            INSERT INTO painel_indicadores
                (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, filtro_clique_variavel_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            RETURNING *
        """, painel_id, ind.query_slug, ind.titulo,
            ind.linha, ind.coluna, ind.col_span, ind.row_span, ind.posicao,
            ind.filtro_clique_variavel_id)
        resultado.append(dict(rows[0]))
    return resultado
```

Em `renderizar_painel`, o `SELECT` (linha 380-391) ganha a coluna nova de `queries` e um segundo `LEFT JOIN` pra resolver slug/tipo da variável-alvo:

```python
    indicadores = await query_meta("""
        SELECT pi.*, q.id AS query_id, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label, q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna,
               q.meta_habilitada, q.meta_coluna_valor, q.meta_coluna_inicio, q.meta_coluna_fim,
               q.meta_cor_dentro, q.meta_cor_fora, q.subquery_id,
               q.pdf_orientacao, q.kpi_imagem_habilitada, q.kpi_imagem_posicao,
               q.chart_filtro_coluna,
               fv.slug AS filtro_clique_variavel_slug, fv.tipo AS filtro_clique_variavel_tipo
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        LEFT JOIN variaveis fv ON fv.id = pi.filtro_clique_variavel_id
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
```

`pi.*` já traz `filtro_clique_variavel_id` sozinho, sem precisar listar explicitamente. Nenhuma outra parte de `renderizar_painel` muda — o `pop` de `query_id`/`subquery_id` (linha 446-448) continua igual, essa feature não depende disso.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec datahub_backend python -m pytest tests/test_paineis_filtro_clique_grafico.py -v`
Expected: PASS

- [ ] **Step 6: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam.

- [ ] **Step 7: Commit**

```bash
git add backend/routes/paineis.py backend/tests/conftest.py backend/tests/test_paineis_filtro_clique_grafico.py
git commit -m "feat: resolve click-to-filter target variable in renderizar_painel"
```

---

## Task 4: Frontend — telas de configuração de query (`nova` e `[id]`): campo `chart_filtro_coluna`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`

**Interfaces:**
- Consumes: `chart_filtro_coluna` do Task 2 (aceito por `criarQuery`/`atualizarQuery`).
- Produces: campo configurável na UI, dentro do bloco "Configurações do Gráfico".

- [ ] **Step 1: `nova/+page.svelte` — form default**

Depois de `chart_valor_label: '',` (linha 15), adicionar:

```js
    chart_filtro_coluna: '',
```

- [ ] **Step 2: `nova/+page.svelte` — campo na UI**

Dentro do bloco `{#if ['chart_bar', 'chart_bar_horizontal', 'chart_line', 'chart_doughnut'].includes(form.tipo)}` (linha 482-512), depois do bloco de `chart_valor_label` (linha 504-509, fecha em `{/if}`) e antes do `</div>` de fechamento de `.cores-row` (linha 510):

```svelte
          <label class="lbl">
            Coluna com o id bruto pro filtro por clique (opcional)
            <select bind:value={form.chart_filtro_coluna}>
              <option value="">— nenhuma —</option>
              {#each resultadoTeste?.colunas ?? (form.chart_filtro_coluna ? [form.chart_filtro_coluna] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
          </label>
```

- [ ] **Step 3: `[id]/+page.svelte` — form default e carregamento**

Depois de `chart_valor_label: '',` no `let form = {...}` (linha 18), adicionar:

```js
    chart_filtro_coluna: '',
```

No `form = {...}` dentro do `onMount` (depois de `chart_valor_label: q.chart_valor_label || '',`, linha 88), adicionar:

```js
        chart_filtro_coluna:   q.chart_filtro_coluna || '',
```

- [ ] **Step 4: `[id]/+page.svelte` — campo na UI**

No mesmo bloco "Configurações do Gráfico" (linha 572-599), depois do bloco de `chart_valor_label` (linha 592-597) e antes do `</div>` de fechamento de `.cores-row` (linha 598):

```svelte
            <label class="lbl">
              Coluna com o id bruto pro filtro por clique (opcional)
              <select bind:value={form.chart_filtro_coluna}>
                <option value="">— nenhuma —</option>
                {#each resultadoTeste?.colunas ?? (form.chart_filtro_coluna ? [form.chart_filtro_coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
```

- [ ] **Step 5: `[id]/+page.svelte` — envio no `salvar()`**

No objeto passado pra `api.atualizarQuery(id, {...})` (depois de `chart_valor_label: form.chart_valor_label,`, linha 231), adicionar:

```js
        chart_filtro_coluna:   form.chart_filtro_coluna || null,
```

- [ ] **Step 6: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 7: Verificação manual**

1. Em `http://localhost:3000/configuracoes/queries/nova`, tipo `chart_bar`, SQL `SELECT 'A' AS label, 10 AS valor, 1 AS categoria_id UNION ALL SELECT 'B', 20, 2`, clicar "Testar" — confirmar que o novo campo "Coluna com o id bruto..." aparece com as opções `label`, `valor`, `categoria_id`.
2. Escolher `categoria_id`, salvar a query.
3. Abrir a mesma query em "Editar" — confirmar que `categoria_id` continua selecionado.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/routes/configuracoes/queries/nova/+page.svelte" "frontend/src/routes/configuracoes/queries/[id]/+page.svelte"
git commit -m "feat: add chart_filtro_coluna field to query config screens"
```

---

## Task 5: Frontend — tela de painel (`configuracoes/paineis/[id]`): campo `filtro_clique_variavel_id` por indicador

**Files:**
- Modify: `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte`

**Interfaces:**
- Consumes: `filtro_clique_variavel_id` do Task 3 (aceito por `salvarIndicadores`); `queries` (já carregado nessa tela) precisa ter `chart_filtro_coluna` do Task 2 pra decidir se mostra o campo.
- Produces: campo "Filtro por clique" por indicador, listando as variáveis já adicionadas ao painel.

- [ ] **Step 1: Default do campo ao carregar indicadores existentes**

No `indicadores = inds.map(...)` dentro do `onMount` (linha 60-68), adicionar:

```js
      indicadores = inds.map(i => ({
        query_slug: i.query_slug,
        titulo:     i.titulo || '',
        linha:      i.linha,
        coluna:     i.coluna,
        col_span:   i.col_span,
        row_span:   i.row_span,
        posicao:    i.posicao,
        filtro_clique_variavel_id: i.filtro_clique_variavel_id ?? null,
      }));
```

- [ ] **Step 2: Default do campo ao adicionar indicador novo**

Em `adicionarIndicador()` (linha 92-98), adicionar:

```js
  function adicionarIndicador() {
    indicadores = [...indicadores, {
      query_slug: queries[0]?.slug || '', titulo: '',
      linha: indicadores.length + 1, coluna: 1,
      col_span: 1, row_span: 1, posicao: indicadores.length,
      filtro_clique_variavel_id: null,
    }];
  }
```

- [ ] **Step 3: Incluir no swap de `moverIndicador`**

`moverIndicador` (linha 111-120) troca `query_slug`/`titulo`/`posicao` entre as duas posições (não troca `col_span`/`row_span`/`linha`/`coluna`, que ficam presos à célula do grid). `filtro_clique_variavel_id` é uma config amarrada a "qual query está aqui", igual `titulo` — adicionar ao swap:

```js
  function moverIndicador(i, direcao) {
    const j = i + direcao;
    if (j < 0 || j >= indicadores.length) return;
    const a = indicadores[i];
    const b = indicadores[j];
    [a.query_slug, b.query_slug] = [b.query_slug, a.query_slug];
    [a.titulo, b.titulo]         = [b.titulo, a.titulo];
    [a.posicao, b.posicao]       = [b.posicao, a.posicao];
    [a.filtro_clique_variavel_id, b.filtro_clique_variavel_id] = [b.filtro_clique_variavel_id, a.filtro_clique_variavel_id];
    indicadores = [...indicadores];
  }
```

- [ ] **Step 4: Lista reativa de variáveis já adicionadas ao painel**

Depois da declaração de `let variaveis = [];` (linha 26) ou em qualquer ponto do `<script>` fora de uma função, adicionar (variáveis-alvo só fazem sentido como `select`/`multiselect`, os únicos tipos com comportamento de clique definido no spec):

```js
  $: variaveisDoPainel = varSelecionadas
    .map(s => variaveis.find(v => v.id === s.variavel_id))
    .filter(v => v && (v.tipo === 'select' || v.tipo === 'multiselect'));
```

- [ ] **Step 5: Campo na UI, por indicador**

Dentro do `{#each indicadores as ind, i}` (linha 287-325), depois do `.grid-4` de linha/coluna/col_span/row_span (fecha em `</div>` na linha 323) e antes do `</div>` de fechamento de `.ind-item` (linha 324):

```svelte
                  {#if queries.find(q => q.slug === ind.query_slug)?.chart_filtro_coluna}
                    <div class="field">
                      <label>Filtro por clique no gráfico</label>
                      <select bind:value={ind.filtro_clique_variavel_id}>
                        <option value={null}>— sem filtro por clique —</option>
                        {#each variaveisDoPainel as v}
                          <option value={v.id}>{v.nome}</option>
                        {/each}
                      </select>
                      <span class="hint">Ao clicar num item do gráfico, aplica o filtro nessa variável (precisa estar marcada na aba "Filtros e Acesso").</span>
                    </div>
                  {/if}
```

- [ ] **Step 6: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 7: Verificação manual**

1. Criar (ou reusar) um painel com a variável `var_fazenda` (ou qualquer `select`/`multiselect`) adicionada na aba "Filtros e Acesso".
2. Na aba "Indicadores", adicionar a query `chart_bar` criada no Task 4 (com `chart_filtro_coluna` configurada) — confirmar que o campo "Filtro por clique no gráfico" aparece, listando `var_fazenda`.
3. Adicionar também uma query `kpi` ou `table` qualquer — confirmar que o campo NÃO aparece pra ela (nem query sem `chart_filtro_coluna`, nem tipo não-gráfico).
4. Escolher a variável no campo, salvar. Recarregar a página — confirmar que a seleção persiste.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/routes/configuracoes/paineis/[id]/+page.svelte"
git commit -m "feat: add click-to-filter target variable field to painel indicator config"
```

---

## Task 6: Frontend — `ChartPanel.svelte`: clique, destaque visual e exclusão da coluna de filtro das séries

**Files:**
- Modify: `frontend/src/lib/components/ChartPanel.svelte`

**Interfaces:**
- Produces: props novas `filtroColuna` (string|null) e `valoresSelecionados` (string[]); evento `filtroClique` com `{ valor }` (o valor bruto da linha clicada, tipo original do SQL — quem consome decide o `String(...)`).
- Comportamento sem `filtroColuna` (`null`, valor default): idêntico ao atual — sem handler de clique ativo, sem mudança visual. Isso garante que os gráficos existentes (todos sem essa prop hoje) não mudam.

- [ ] **Step 1: Substituir o `<script>` inteiro do componente**

Arquivo tem 127 linhas hoje; substituir do início até o fechamento de `</script>` (linhas 1-125) por:

```svelte
<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import * as echarts from 'echarts';
  import { usuario } from '$lib/stores/auth.js';

  export let tipo = 'bar';
  export let dados = [];
  export let fonteTamanho = 12;
  export let truncarLabel = false;
  export let truncarTamanho = 15;
  export let mostrarValor = false;
  export let valorLabel = null;
  export let filtroColuna = null;
  export let valoresSelecionados = [];

  const dispatch = createEventDispatcher();

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

  // Nome de exibição de uma coluna de série: a coluna 'valor' pode ter um
  // nome customizado (valorLabel); as demais sempre mostram o próprio alias SQL.
  function nomeSerie(col) {
    return col === 'valor' && valorLabel ? valorLabel : col;
  }

  // Opacidade de um item clicável: com alguma seleção ativa, o item
  // selecionado fica cheio e os demais apagam; sem seleção, todos cheios.
  function opacidadeClique(d) {
    if (!filtroColuna || !valoresSelecionados.length) return 1;
    return valoresSelecionados.includes(String(d[filtroColuna])) ? 1 : 0.35;
  }

  // Colunas de série: todas as chaves de dados[0] exceto 'label' e a coluna
  // reservada pro filtro por clique (não é série, é o id bruto do clique),
  // que tenham valor numérico em pelo menos uma linha. 'valor' sempre entra
  // primeiro (compatibilidade com queries existentes).
  function colunasSerie(dados, multiSerie) {
    if (!dados.length) return ['valor'];
    const chaves = Object.keys(dados[0]).filter(k => k !== 'label' && k !== filtroColuna);
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
    const cursor = filtroColuna ? 'pointer' : 'default';

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
          type: 'pie', radius: ['45%', '70%'], cursor,
          data: dados.map((d, i) => ({
            value: Number(d[colValor]), name: d.label,
            itemStyle: { color: COLORS[i % COLORS.length], opacity: opacidadeClique(d) },
          })),
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
      name: nomeSerie(col),
      cursor,
      data: dados.map(d => filtroColuna
        ? { value: Number(d[col]), itemStyle: { opacity: opacidadeClique(d) } }
        : Number(d[col])),
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
      legend: multiSerie ? { data: cols.map(nomeSerie), top: 0, textStyle: { color: corTexto, fontSize: fonteTamanho } } : undefined,
      grid: { left: 60, right: 20, top: multiSerie ? 40 : 20, bottom: 40 },
      xAxis: isHorizontal ? eixoValor : eixoCategoria,
      yAxis: isHorizontal ? eixoCategoria : eixoValor,
      series,
    };
  }

  function onClickGrafico(params) {
    if (!filtroColuna) return;
    const row = dados[params.dataIndex];
    if (!row) return;
    dispatch('filtroClique', { valor: row[filtroColuna] });
  }

  onMount(() => {
    chart = echarts.init(container, null, { renderer: 'svg' });
    chart.on('click', onClickGrafico);
    if (dados.length) chart.setOption(buildOption(tipo, dados));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(container);
    return () => ro.disconnect();
  });

  $: if (chart && dados.length) {
    $usuario?.tema;        // dependência reativa: recria a option quando o tema muda
    filtroColuna;           // dependência reativa: recria quando a coluna de filtro muda
    valoresSelecionados;    // dependência reativa: recria quando a seleção de clique muda
    chart.setOption(buildOption(tipo, dados), true);
  }

  onDestroy(() => chart?.dispose());
</script>
```

O `<div bind:this={container} ...>` no final do arquivo (linha 127) não muda.

- [ ] **Step 2: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 3: Verificação manual de regressão**

Abrir qualquer painel existente com gráficos de barra/rosca/linha (ex: `visao_geral`) — confirmar que continuam renderizando exatamente como antes (nenhuma prop nova é passada ainda nesse ponto do plano, então `filtroColuna` é `null` e o comportamento deve ser idêntico ao anterior: sem cursor de mão, sem opacidade reduzida, cliques não fazem nada).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/ChartPanel.svelte
git commit -m "feat: add click-to-filter interaction to ChartPanel"
```

---

## Task 7: Frontend — encaixe no painel (`painel/[slug]/+page.svelte`) + verificação manual completa

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `ChartPanel` (Task 6) props `filtroColuna`/`valoresSelecionados`/evento `filtroClique`; campos do indicador vindos de `renderizar_painel` (Task 3): `chart_filtro_coluna`, `filtro_clique_variavel_slug`, `filtro_clique_variavel_tipo`.

- [ ] **Step 1: Funções de leitura/escrita do filtro por clique**

Depois de `onFiltroMudou` (linha 154-156), adicionar:

```js
  function valoresClicados(ind) {
    const slug = ind.filtro_clique_variavel_slug;
    if (!slug) return [];
    const val = filtrosAtivos[slug];
    if (!val) return [];
    return ind.filtro_clique_variavel_tipo === 'multiselect' ? String(val).split(',') : [String(val)];
  }

  function onFiltroClique(ind, valorBruto) {
    const slug = ind.filtro_clique_variavel_slug;
    if (!slug) return;
    const valor = String(valorBruto);
    if (ind.filtro_clique_variavel_tipo === 'multiselect') {
      const atuais = filtrosAtivos[slug] ? filtrosAtivos[slug].split(',').filter(Boolean) : [];
      const idx = atuais.indexOf(valor);
      const novos = idx >= 0 ? atuais.filter((_, i) => i !== idx) : [...atuais, valor];
      filtrosAtivos = { ...filtrosAtivos, [slug]: novos.join(',') };
    } else {
      filtrosAtivos = { ...filtrosAtivos, [slug]: filtrosAtivos[slug] === valor ? '' : valor };
    }
    carregarDados();
  }
```

- [ ] **Step 2: Passar as props novas pro `ChartPanel`**

No bloco `{:else if ind.query_tipo?.startsWith('chart_')}` (linha 255-264):

```svelte
            {:else if ind.query_tipo?.startsWith('chart_')}
              <ChartPanel
                tipo={ind.query_tipo}
                dados={ind.dados}
                fonteTamanho={ind.chart_fonte_tamanho}
                truncarLabel={ind.chart_truncar_label}
                truncarTamanho={ind.chart_truncar_tamanho}
                mostrarValor={ind.chart_mostrar_valor}
                valorLabel={ind.chart_valor_label}
                filtroColuna={ind.chart_filtro_coluna}
                valoresSelecionados={valoresClicados(ind)}
                on:filtroClique={(e) => onFiltroClique(ind, e.detail.valor)}
              />
```

- [ ] **Step 3: Restart do frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 4: Verificação manual completa**

1. Confirmar (Task 4) que existe uma query `chart_bar` com `chart_filtro_coluna` configurada, agrupando por uma coluna de texto que também é o `label` de alguma variável `select`/`multiselect` real do projeto — ex: usar `propriedade_id` como `chart_filtro_coluna` num gráfico que agrupa por fazenda, testando na empresa `prats` (tem dados reais recentes, ver memória do projeto), pra poder cruzar com `var_fazenda`.
2. Confirmar (Task 5) que o painel usado tem essa variável marcada em "Filtros e Acesso" e o indicador do gráfico aponta pra ela em "Filtro por clique no gráfico".
3. Abrir o painel (`http://localhost:3000/painel/<slug>`) — passar o mouse sobre uma barra/fatia: cursor deve virar "mão" (`pointer`).
4. Clicar numa barra — confirmar: (a) o painel recarrega os outros indicadores filtrados por aquele valor; (b) a barra clicada fica com opacidade cheia e as outras ficam apagadas; (c) o chip de resumo de filtros no topo mostra o valor selecionado; (d) o botão "Filtros" expandido mostra a mesma seleção no dropdown da variável.
5. Se a variável for `multiselect`: clicar numa segunda barra — confirmar que ambas ficam selecionadas (toggle acumula) e os outros indicadores agora filtram pelas duas.
6. Clicar de novo numa barra já selecionada — confirmar que ela é removida da seleção (toggle remove) e os indicadores recarregam sem esse valor.
7. Clicar em "Limpar filtros" — confirmar que a seleção do gráfico some (opacidade volta ao normal em todas as barras) e os outros indicadores voltam ao estado padrão.
8. Confirmar que um gráfico SEM `chart_filtro_coluna` configurada (ou sem `filtro_clique_variavel_id` no indicador) continua sem cursor de mão e sem reagir a clique.
9. Confirmar que `kpi`, `table`, `table_dynamic` e `map` continuam funcionando sem regressão visual.

- [ ] **Step 5: Reverter dados de teste**

Apagar (ou desconfigurar) a query/indicador/variável criados só pra este teste, se não fizerem parte de um painel real do usuário (Configurações → Queries / Painéis).

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: wire click-to-filter interaction into painel view"
```
