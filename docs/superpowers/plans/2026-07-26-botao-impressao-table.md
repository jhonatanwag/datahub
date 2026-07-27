# Botão de Impressão em Queries Tipo `table` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que uma query tipo `table` mostre, opcionalmente, um botão de impressão por linha que monta um link concatenando a URL base cadastrada na empresa + o caminho do relatório cadastrado na query + o UUID vindo de uma coluna do próprio resultado.

**Architecture:** Três colunas novas persistidas no `datahub_meta` (`empresas.url_impressao_base`, `queries.impressao_habilitada`, `queries.impressao_caminho`, `queries.impressao_coluna`), propagadas via `GET /api/auth/me` e `GET /api/paineis/{id}/renderizar` (mesmo padrão já usado por `kpi_cor_fonte`/`chart_valor_label`/`mapa_camada`), consumidas por `DataTable.svelte` que concatena as três partes e renderiza um botão por linha — sem persistir o link calculado em nenhum lugar.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, asyncpg, PostgreSQL, pytest

## Global Constraints

- Campos só fazem sentido quando `queries.tipo = 'table'`, mas as colunas existem em todas as linhas de `queries` (mesmo padrão de `kpi_cor_fonte`/`mapa_camada`)
- Sem validação de que `impressao_coluna` existe de fato nos dados retornados pela query — falha silenciosa (célula/botão só não aparece)
- Empresa sem `url_impressao_base` cadastrada → botão não aparece, mesmo com a query habilitada
- Linha sem valor na coluna do UUID → sem botão só nessa linha, resto da tabela funciona normal
- Link sempre abre em nova aba (`window.open(url, '_blank')`)
- Coluna do UUID nunca aparece como dado visível na tabela nem no export CSV/Excel
- Sem sistema de migrations — `ALTER TABLE` manual + refletir em `scripts/init-db.sql`, `scripts/init-meta-prod.sql` e README ("Deltas de schema pendentes")

---

## Task 1: Empresas — `url_impressao_base`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`
- Modify: `backend/routes/empresas.py`
- Test: `backend/tests/test_empresas_url_impressao.py`

**Interfaces:**
- Produces: coluna `empresas.url_impressao_base` (TEXT, nullable); `EmpresaInput.url_impressao_base: str | None`; `EmpresaUpdate.url_impressao_base: str | None`; `GET/POST/PATCH /api/empresas/*` passam a incluir `url_impressao_base` na resposta.

- [ ] **Step 1: Schema (dev + scripts)**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE empresas ADD COLUMN url_impressao_base TEXT;"
```

Em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`, no bloco `CREATE TABLE empresas`, adicionar logo após `sso_query_acesso TEXT,`:

```sql
    url_impressao_base TEXT
```

Em `README.md`, seção "Deltas de schema pendentes", adicionar ao final do bloco de `SELECT column_name ... WHERE table_name = 'empresas'`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'empresas'
  AND column_name IN ('sso_api_key_hash', 'sso_query_acesso', 'url_impressao_base');
```

E no bloco de `ALTER TABLE` a aplicar:

```sql
-- 2026-07-26 — URL base do sistema legado de impressão de relatórios, por empresa
ALTER TABLE empresas ADD COLUMN url_impressao_base TEXT;
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_empresas_url_impressao.py`:

```python
def test_atualizar_empresa_com_url_impressao_base_persiste_e_devolve(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")
    atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()

    payload_base = {
        "slug": atual["slug"], "nome": atual["nome"], "db_host": atual["db_host"],
        "db_port": atual["db_port"], "db_name": atual["db_name"], "db_user": atual["db_user"],
        "ativo": atual["ativo"],
    }

    try:
        res = client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": "https://www.psosistemas.com.br:8443/Alpha/"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200

        verificar = client.get(
            f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
        ).json()
        assert verificar["url_impressao_base"] == "https://www.psosistemas.com.br:8443/Alpha/"
    finally:
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": atual.get("url_impressao_base")},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_url_impressao.py -v`
Expected: FAIL — `KeyError: 'url_impressao_base'` (campo ainda não existe na resposta, Pydantic descarta o campo desconhecido no `EmpresaUpdate` e `buscar_empresa` não seleciona a coluna).

- [ ] **Step 4: Implement — `backend/routes/empresas.py`**

`EmpresaInput`: adicionar `url_impressao_base: str | None = None` (após `ativo: bool = True`).

`EmpresaUpdate`: adicionar `url_impressao_base: str | None = None` (após `sso_query_acesso`).

`buscar_empresa` — incluir a coluna no SELECT:

```python
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, db_user, ativo, criado_em, sso_query_acesso, url_impressao_base FROM empresas WHERE id = $1",
        id
    )
```

`criar_empresa` — incluir no INSERT:

```python
        rows = await query_meta("""
            INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo, url_impressao_base)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo, body.url_impressao_base)
```

`atualizar_empresa` — incluir no UPDATE:

```python
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6,
                db_pass=COALESCE($7, db_pass),
                ativo=$8,
                sso_query_acesso=$9,
                url_impressao_base=$10
            WHERE id=$11
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo,
            body.sso_query_acesso, body.url_impressao_base, id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_url_impressao.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md backend/routes/empresas.py backend/tests/test_empresas_url_impressao.py
git commit -m "feat: add url_impressao_base field to empresas"
```

---

## Task 2: Queries — `impressao_habilitada` / `impressao_caminho` / `impressao_coluna`

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`
- Modify: `backend/routes/queries.py`
- Test: `backend/tests/test_queries_impressao.py`

**Interfaces:**
- Produces: colunas `queries.impressao_habilitada` (BOOLEAN DEFAULT false), `queries.impressao_caminho` (TEXT nullable), `queries.impressao_coluna` (TEXT nullable); `QueryInput`/`QueryUpdate` com os três campos; `POST/PATCH/GET /api/queries/*` passam a incluir os três campos na resposta.
- Independente do Task 1 — pode ser feito em paralelo.

- [ ] **Step 1: Schema (dev + scripts)**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE queries ADD COLUMN impressao_habilitada BOOLEAN DEFAULT false; ALTER TABLE queries ADD COLUMN impressao_caminho TEXT; ALTER TABLE queries ADD COLUMN impressao_coluna TEXT;"
```

Em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`, no bloco `CREATE TABLE queries`, adicionar logo após `chart_valor_label VARCHAR(50),`:

```sql
    impressao_habilitada  BOOLEAN DEFAULT false,
    impressao_caminho     TEXT,
    impressao_coluna      TEXT
```

Em `README.md`, seção "Deltas de schema pendentes", adicionar ao bloco de `SELECT column_name ... WHERE table_name = 'queries'`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'queries'
  AND column_name IN ('mapa_camada', 'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor', 'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna');
```

E no bloco de `ALTER TABLE` a aplicar:

```sql
-- 2026-07-26 — botão de impressão opcional em queries tipo table (link pro sistema legado de relatórios)
ALTER TABLE queries ADD COLUMN impressao_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN impressao_caminho TEXT;
ALTER TABLE queries ADD COLUMN impressao_coluna TEXT;
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_queries_impressao.py`:

```python
TABLE_SQL = "SELECT '1642d8a9-a204-4745-b446-64232422a886' AS uuid, 'Item A' AS descricao"


def test_criar_query_table_com_impressao_habilitada(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_habilitada",
            "nome": "Teste Impressão",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is True
    assert body["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
    assert body["impressao_coluna"] == "uuid"
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_criar_query_table_sem_impressao_fica_desabilitada_por_padrao(client, auth_token):
    res = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_default",
            "nome": "Teste Impressão Default",
            "sql_texto": TABLE_SQL,
            "tipo": "table",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is False
    assert body["impressao_caminho"] is None
    assert body["impressao_coluna"] is None
    client.delete(f"/api/queries/{body['id']}", headers={"Authorization": f"Bearer {auth_token}"})


def test_atualizar_query_campos_de_impressao(client, auth_token):
    criar = client.post(
        "/api/queries/",
        json={
            "slug": "teste_impressao_update",
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
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["impressao_habilitada"] is True
    assert body["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
    assert body["impressao_coluna"] == "uuid"

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_impressao.py -v`
Expected: FAIL — os três campos não existem em `QueryInput`/`QueryUpdate`, então são descartados silenciosamente pelo Pydantic e não aparecem na resposta (`KeyError`/`AssertionError`).

- [ ] **Step 4: Implement — `backend/routes/queries.py`**

`QueryInput`: adicionar (após `chart_valor_label`):

```python
    impressao_habilitada: bool = False
    impressao_caminho: Optional[str] = None
    impressao_coluna: Optional[str] = None
```

`QueryUpdate`: adicionar os mesmos três campos, todos opcionais:

```python
    impressao_habilitada: Optional[bool] = None
    impressao_caminho: Optional[str] = None
    impressao_coluna: Optional[str] = None
```

`atualizar_query` — incluir os três em `ALLOWED_COLS`:

```python
        ALLOWED_COLS = {
            'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo',
            'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada',
            'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor',
            'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna'
        }
```

`criar_query` — incluir no INSERT (agora 19 colunas):

```python
        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor,
                chart_valor_label, impressao_habilitada, impressao_caminho, impressao_coluna
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo,
            body.kpi_cor_fonte, body.kpi_cor_fundo, body.mapa_camada,
            body.chart_fonte_tamanho, body.chart_truncar_label,
            body.chart_truncar_tamanho, body.chart_mostrar_valor,
            body.chart_valor_label, body.impressao_habilitada,
            body.impressao_caminho, body.impressao_coluna)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker exec datahub_backend python -m pytest tests/test_queries_impressao.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md backend/routes/queries.py backend/tests/test_queries_impressao.py
git commit -m "feat: add print button config fields to queries"
```

---

## Task 3: Propagar os campos — `middleware/auth.py` e `paineis.py`

**Files:**
- Modify: `backend/middleware/auth.py`
- Modify: `backend/routes/paineis.py`
- Test: `backend/tests/test_impressao_middleware_e_painel.py`

**Interfaces:**
- Consumes: `empresas.url_impressao_base` (Task 1), `queries.impressao_habilitada/impressao_caminho/impressao_coluna` (Task 2) — ambas precisam estar concluídas antes deste task.
- Produces: `GET /api/auth/me` inclui `url_impressao_base` no payload do usuário; cada item de `GET /api/paineis/{id}/renderizar` → `indicadores[]` inclui `impressao_habilitada`, `impressao_caminho`, `impressao_coluna`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_impressao_middleware_e_painel.py`:

```python
import uuid
from conftest import hard_delete_painel


def test_me_inclui_url_impressao_base_da_empresa_ativa(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")
    atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    payload_base = {
        "slug": atual["slug"], "nome": atual["nome"], "db_host": atual["db_host"],
        "db_port": atual["db_port"], "db_name": atual["db_name"], "db_user": atual["db_user"],
        "ativo": atual["ativo"],
    }

    try:
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": "https://www.psosistemas.com.br:8443/Alpha/"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert res.status_code == 200
        assert res.json()["url_impressao_base"] == "https://www.psosistemas.com.br:8443/Alpha/"
    finally:
        client.patch(
            f"/api/empresas/{alpha['id']}",
            json={**payload_base, "url_impressao_base": atual.get("url_impressao_base")},
            headers={"Authorization": f"Bearer {auth_token}"},
        )


def test_renderizar_painel_inclui_campos_de_impressao_do_indicador(client, auth_token):
    query_slug = f"query_impressao_painel_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query Impressão Painel",
            "sql_texto": "SELECT '1642d8a9-a204-4745-b446-64232422a886' AS uuid, 'Item A' AS descricao",
            "tipo": "table",
            "cache_ttl": 0,
            "impressao_habilitada": True,
            "impressao_caminho": "relatorioPerda/Impressao.xhtml?uuid=",
            "impressao_coluna": "uuid",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    painel_slug = f"painel_impressao_{uuid.uuid4().hex[:8]}"
    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel Impressão"},
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
        assert indicador["impressao_habilitada"] is True
        assert indicador["impressao_caminho"] == "relatorioPerda/Impressao.xhtml?uuid="
        assert indicador["impressao_coluna"] == "uuid"
    finally:
        hard_delete_painel(painel_id)
        client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec datahub_backend python -m pytest tests/test_impressao_middleware_e_painel.py -v`
Expected: FAIL — `url_impressao_base` ausente do payload de `/me` (middleware ainda não seleciona a coluna), e `impressao_*` ausentes de cada indicador (JOIN de `renderizar_painel` ainda não traz essas colunas).

- [ ] **Step 3: Implement — `backend/middleware/auth.py`**

No bloco de usuário externo (`tipo == "externo"`), incluir a coluna no SELECT e no dict devolvido:

```python
        empresa_rows = await query_meta(
            "SELECT id, nome, slug, url_impressao_base FROM empresas WHERE id = $1 AND ativo = true",
            empresa_id
        )
        if not empresa_rows:
            raise HTTPException(status_code=403, detail="Acesso negado")
        empresa = dict(empresa_rows[0])

        return {
            "id": None,
            "nome": None,
            "role": "externo",
            "tema": None,
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "company_name": empresa["nome"],
            "url_impressao_base": empresa["url_impressao_base"],
            "codigo_usuario": codigo_usuario,
            "paineis_liberados": paineis_liberados,
        }
```

No bloco de usuário interno, incluir a coluna no SELECT:

```python
    rows = await query_meta("""
        SELECT u.id, u.nome, u.role, u.tema,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name,
               e.url_impressao_base,
               ue.codigo_usuario_externo
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, user_id, empresa_id)
```

- [ ] **Step 4: Implement — `backend/routes/paineis.py`**

Em `renderizar_painel`, incluir as três colunas no `SELECT` que já traz `chart_valor_label`:

```python
    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label, q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec datahub_backend python -m pytest tests/test_impressao_middleware_e_painel.py -v`
Expected: PASS

- [ ] **Step 6: Run full backend suite to check for regressions**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes passam (nenhuma regressão nas queries de `/me` ou `renderizar_painel` usadas por outros testes, ex: SSO externo e `codigo_usuario_externo`).

- [ ] **Step 7: Commit**

```bash
git add backend/middleware/auth.py backend/routes/paineis.py backend/tests/test_impressao_middleware_e_painel.py
git commit -m "feat: propagate print button fields through /me and renderizar_painel"
```

---

## Task 4: Frontend — telas de configuração, `DataTable.svelte` e painel

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`
- Modify: `frontend/src/routes/selecionar-empresa/+page.svelte`
- Modify: `frontend/src/routes/sso/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/empresas/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`
- Modify: `frontend/src/lib/components/DataTable.svelte`
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `me.url_impressao_base` (Task 3), `ind.impressao_habilitada`/`ind.impressao_caminho`/`ind.impressao_coluna` de cada indicador retornado por `renderizar_painel` (Task 3).
- Sem testes automatizados — projeto não tem framework de teste de frontend. Verificação manual via navegador (ver Step 8).

- [ ] **Step 1: `empresaAtiva` — incluir `url_impressao_base` nos 3 lugares que montam o objeto**

`frontend/src/routes/+layout.svelte` (linha ~86):

```js
          empresaAtiva.set({
            id: me.empresa_id, slug: me.company_slug,
            nome: me.company_name,
            logo_url: `/api/empresas/${me.empresa_id}/logo`,
            url_impressao_base: me.url_impressao_base ?? null
          });
```

`frontend/src/routes/selecionar-empresa/+page.svelte` (linha ~38):

```js
      empresaAtiva.set({ id: empresa.id, slug: empresa.slug, nome: empresa.nome, logo_url: empresa.logo_url, url_impressao_base: me.url_impressao_base ?? null });
```

`frontend/src/routes/sso/+page.svelte` (linha ~20):

```js
      empresaAtiva.set({
        id: me.empresa_id, slug: me.company_slug,
        nome: me.company_name,
        logo_url: `/api/empresas/${me.empresa_id}/logo`,
        url_impressao_base: me.url_impressao_base ?? null
      });
```

- [ ] **Step 2: Tela de empresas — campo `url_impressao_base`**

`frontend/src/routes/configuracoes/empresas/nova/+page.svelte`:

Adicionar variável local após `let db_pass = '';`:

```js
  let url_impressao_base = '';
```

Na seção "Dados da Empresa", após o campo de logo, adicionar:

```svelte
      <label>
        URL base de impressão (opcional)
        <input bind:value={url_impressao_base} placeholder="https://www.psosistemas.com.br:8443/NomeDaEmpresa/" />
      </label>
```

Em `salvar()`, incluir no payload:

```js
      const empresa = await api.criarEmpresa({ slug, nome, db_host, db_port, db_name, db_user, db_pass, url_impressao_base: url_impressao_base || null });
```

`frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`:

Na seção "Dados da Empresa", após o campo de logo, adicionar:

```svelte
        <label>
          URL base de impressão (opcional)
          <input bind:value={empresa.url_impressao_base} placeholder="https://www.psosistemas.com.br:8443/NomeDaEmpresa/" />
        </label>
```

Em `salvar()`, incluir no payload:

```js
      const payload = {
        slug:    empresa.slug,
        nome:    empresa.nome,
        db_host: empresa.db_host,
        db_port: empresa.db_port,
        db_name: empresa.db_name,
        db_user: empresa.db_user,
        ativo:   empresa.ativo,
        sso_query_acesso: empresa.sso_query_acesso ?? null,
        url_impressao_base: empresa.url_impressao_base ?? null,
      };
```

- [ ] **Step 3: Tela de queries — seção "Botão de Impressão"**

`frontend/src/routes/configuracoes/queries/nova/+page.svelte`:

No `form`, adicionar após `chart_valor_label: ''`:

```js
    impressao_habilitada: false, impressao_caminho: '', impressao_coluna: ''
```

Depois do bloco `{#if form.tipo === 'map'}` e antes do bloco de gráfico, adicionar:

```svelte
    {#if form.tipo === 'table'}
      <div class="section-block">
        <span class="section-title">Botão de Impressão</span>
        <label class="check-inline">
          <input type="checkbox" bind:checked={form.impressao_habilitada} />
          Habilitar botão de impressão nesta tabela
        </label>
        {#if form.impressao_habilitada}
          <label class="lbl">
            Caminho do relatório (concatenado após a URL base da empresa)
            <input type="text" bind:value={form.impressao_caminho} placeholder="relatorioPerda/Impressao.xhtml?uuid=" />
          </label>
          <label class="lbl">
            Coluna com o UUID/link (teste a query pra ver as colunas disponíveis)
            <select bind:value={form.impressao_coluna}>
              <option value="">— selecione —</option>
              {#each resultadoTeste?.colunas ?? (form.impressao_coluna ? [form.impressao_coluna] : []) as c}
                <option value={c}>{c}</option>
              {/each}
            </select>
          </label>
          <p class="hint-block">
            A coluna escolhida fica oculta na tabela do painel — usada só pra montar o link. O link final é
            <code>URL base da empresa + caminho acima + valor da coluna</code>. Sem URL base cadastrada na
            empresa (Configurações → Empresas), o botão não aparece pra ela, mesmo com o recurso habilitado aqui.
          </p>
        {/if}
      </div>
    {/if}
```

`frontend/src/routes/configuracoes/queries/[id]/+page.svelte`:

No `form` do `onMount`, adicionar após `chart_valor_label: q.chart_valor_label || ''`:

```js
        impressao_habilitada: q.impressao_habilitada ?? false,
        impressao_caminho:    q.impressao_caminho || '',
        impressao_coluna:     q.impressao_coluna || '',
```

Depois do bloco `{#if form.tipo === 'map'}` e antes do bloco de gráfico, adicionar o mesmo bloco de template do Step 3 (arquivo `nova/+page.svelte`):

```svelte
      {#if form.tipo === 'table'}
        <div class="section-block">
          <span class="section-title">Botão de Impressão</span>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.impressao_habilitada} />
            Habilitar botão de impressão nesta tabela
          </label>
          {#if form.impressao_habilitada}
            <label class="lbl">
              Caminho do relatório (concatenado após a URL base da empresa)
              <input type="text" bind:value={form.impressao_caminho} placeholder="relatorioPerda/Impressao.xhtml?uuid=" />
            </label>
            <label class="lbl">
              Coluna com o UUID/link (teste a query pra ver as colunas disponíveis)
              <select bind:value={form.impressao_coluna}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.impressao_coluna ? [form.impressao_coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <p class="hint-block">
              A coluna escolhida fica oculta na tabela do painel — usada só pra montar o link. O link final é
              <code>URL base da empresa + caminho acima + valor da coluna</code>. Sem URL base cadastrada na
              empresa (Configurações → Empresas), o botão não aparece pra ela, mesmo com o recurso habilitado aqui.
            </p>
          {/if}
        </div>
      {/if}
```

Note a indentação de 6 espaços (em vez de 4) — o template de `[id]/+page.svelte` já está um nível a mais aninhado dentro do `{#if carregando}...{:else}`, diferente de `nova/+page.svelte`.

Em `salvar()`, incluir no payload de `atualizarQuery`:

```js
        impressao_habilitada: form.impressao_habilitada,
        impressao_caminho:    form.impressao_caminho || null,
        impressao_coluna:     form.impressao_coluna || null,
```

- [ ] **Step 4: `DataTable.svelte` — coluna oculta + botão de impressão**

Adicionar novas props (após `export let titulo = 'dados';`):

```js
  export let impressaoHabilitada = false;
  export let impressaoUrlBase    = null;
  export let impressaoColuna     = null;
```

Alterar o cálculo de `colunasEfetivas` para sempre excluir `impressaoColuna`, independente da origem (explícita ou derivada):

```js
  $: colunasEfetivas = (colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
  ).filter(c => c.key !== impressaoColuna);

  $: mostrarAcoes = impressaoHabilitada && !!impressaoUrlBase && !!impressaoColuna;

  function imprimir(row) {
    const valor = row[impressaoColuna];
    if (!valor) return;
    window.open(`${impressaoUrlBase}${valor}`, '_blank');
  }
```

No `<thead>`, depois do `{#each colunasEfetivas as col}`:

```svelte
        {#if mostrarAcoes}<th>Ações</th>{/if}
```

No `<tbody>`, depois do `{#each colunasEfetivas as col}` de cada linha:

```svelte
            {#if mostrarAcoes}
              <td>
                {#if row[impressaoColuna]}
                  <button class="btn-ghost btn-sm" on:click={() => imprimir(row)} title="Imprimir">🖨</button>
                {/if}
              </td>
            {/if}
```

- [ ] **Step 5: `painel/[slug]/+page.svelte` — passar as props pro `DataTable`**

Adicionar import (junto dos outros stores/lib):

```js
  import { empresaAtiva } from '$lib/stores/auth.js';
```

Substituir a linha do `DataTable` (linha ~242):

```svelte
            {:else if ind.query_tipo === 'table'}
              <DataTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                impressaoHabilitada={ind.impressao_habilitada}
                impressaoUrlBase={
                  ind.impressao_habilitada && $empresaAtiva?.url_impressao_base && ind.impressao_caminho
                    ? `${$empresaAtiva.url_impressao_base}${ind.impressao_caminho}`
                    : null
                }
                impressaoColuna={ind.impressao_coluna}
              />
```

- [ ] **Step 6: Rebuild dos containers de dev**

```bash
docker restart datahub_backend datahub_frontend
```

(Bind-mount no Windows não dispara HMR de forma confiável — restart do frontend é obrigatório depois de qualquer edição em `.svelte`/`.js`, ver armadilha documentada no projeto.)

- [ ] **Step 7: Verificação manual completa**

1. Em Configurações → Empresas → editar `alpha`, preencher "URL base de impressão" com `http://localhost:9999/Teste/` (qualquer valor, só pra testar o fluxo), salvar.
2. Em Configurações → Queries → nova query tipo `table`, SQL `SELECT '1642d8a9-a204-4745-b446-64232422a886' AS uuid, 'Pedido A' AS descricao, 100 AS valor`, empresa `alpha`. Clicar "Testar" — confirmar que o dropdown "Coluna com o UUID/link" mostra `uuid`, `descricao`, `valor`. Habilitar impressão, escolher coluna `uuid`, caminho `relatorio/Impressao.xhtml?uuid=`. Salvar.
3. Criar um painel novo, adicionar essa query como indicador, abrir o painel.
4. Confirmar: a tabela mostra as colunas `descricao`/`valor` normalmente, **sem** coluna `uuid` visível, e uma coluna extra "Ações" com o botão 🖨.
5. Clicar no botão — confirmar que abre nova aba em `http://localhost:9999/Teste/relatorio/Impressao.xhtml?uuid=1642d8a9-a204-4745-b446-64232422a886`.
6. Exportar CSV/Excel da mesma tabela — confirmar que nem a coluna `uuid` nem "Ações" aparecem no arquivo.
7. Editar a empresa `alpha` de volta, apagar a "URL base de impressão" (deixar em branco), salvar. Recarregar o painel — confirmar que a coluna "Ações" desaparece (sem quebrar o resto da tabela).
8. Editar a query e desmarcar "Habilitar botão de impressão", salvar. Recarregar o painel — confirmar comportamento idêntico a uma tabela normal, sem coluna de ação.
9. Confirmar que KPI, gráficos e mapa (outros tipos de query) continuam funcionando sem alteração visual.

- [ ] **Step 8: Reverter dados de teste**

Apagar a query de teste criada no passo 7.2 (Configurações → Queries) e o painel criado no passo 7.3 (Configurações → Painéis), pra não deixar lixo de teste manual no banco de dev compartilhado.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/+layout.svelte frontend/src/routes/selecionar-empresa/+page.svelte frontend/src/routes/sso/+page.svelte frontend/src/routes/configuracoes/empresas/nova/+page.svelte "frontend/src/routes/configuracoes/empresas/[id]/+page.svelte" frontend/src/routes/configuracoes/queries/nova/+page.svelte "frontend/src/routes/configuracoes/queries/[id]/+page.svelte" frontend/src/lib/components/DataTable.svelte "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "feat: add optional print button to table-type query panels"
```
