# Impressão de painel + PDF padronizado de tabelas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao DataHub uma saída impressa/PDF moderna e padronizada — botão "Imprimir" no painel (todos os indicadores) e o botão "PDF" das tabelas — as duas usando o mesmo cabeçalho de identidade (faixa verde + logo + dados da empresa), via uma rota de relatório em HTML que abre em nova aba e usa `window.print()`.

**Architecture:** Rota nova `/relatorio/painel/[slug]` renderiza numa aba isolada, sem a sidebar do app, com a paleta verde-clara do padrão forçada no `<html>`. Ela rebusca os dados do painel (`api.renderizarPainel`, a mesma chamada da tela do painel), monta `RelatorioCabecalho` + o grid de indicadores (reusando `KPICard/ChartPanel/DataTable/DynamicTable/MapPanel`) + `RelatorioRodape`, e libera o botão "Imprimir / Salvar PDF" quando gráficos e mapa terminaram de renderizar. O PDF cru de jsPDF/autoTable das tabelas é removido; o botão passa a abrir `/relatorio/painel/<slug>?indicador=<id>`.

**Tech Stack:** SvelteKit (Svelte 5, adapter-static, SPA — sem SSR, sem TypeScript, JS puro), FastAPI + asyncpg, PostgreSQL `datahub_meta`, ECharts (renderer SVG), Leaflet, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-impressao-relatorio-painel-design.md`

## Global Constraints

- **Frontend sem TypeScript** — JS puro em todo `.svelte` / `.js`.
- **Após QUALQUER edição em `frontend/src/`**, rodar `docker restart datahub_frontend` antes de testar — o watcher do Vite não pega mudança de bind-mount no Windows (armadilha documentada na memória do projeto). `docker restart datahub_backend` não tem esse problema.
- **Testes backend:** `docker exec datahub_backend python -m pytest tests/ -v`.
- **Login de teste:** `admin@datahub.local` / `admin123`; empresas `alpha` (seed) ou `prats` (dados reais recentes).
- **Limpeza de teste:** criar/apagar linhas de `empresas` em teste **só** via helper de hard-delete do `conftest.py` (`DELETE` real), nunca via `DELETE /api/empresas/{id}` (que é soft-delete e deixa lixo permanente no banco de dev compartilhado).
- **Paleta do relatório:** sempre a verde-clara do padrão (`--bg: #F4F6F2`, faixa `#1F3D2B→#2E5E3E`, verde `#2E5E3E`, rótulo `#8A968A`, borda `#E3E8E1`, texto `#2B2B2B`), independente do tema do app.
- **Cores dos indicadores mantidas:** `KPICard` continua recebendo `kpi_cor_fonte`/`kpi_cor_fundo`; `ChartPanel` mantém sua paleta. Sem modo "cor neutra".
- **Textos fixos exatos:**
  - Subtítulo do cabeçalho: `RELATÓRIO DE INDICADORES` (painel inteiro) / `RELAÇÃO DE DADOS` (indicador único).
  - Rodapé esquerdo: `DataHub · GPA Analytics`.
  - Rodapé direito: `Relatório gerado eletronicamente · <DD/MM/AAAA HH:MM>`.
  - Cabeçalho, canto direito: `Emitido em <DD/MM/AAAA> às <HH:MM>` (o formato do `Intl.DateTimeFormat('pt-BR', { dateStyle:'short', timeStyle:'short' })` já entrega `08/09/2026 12:42` — usar como está, sem o "às").
- **Só `table` e `table_dynamic`** ganham botão de export PDF individual.
- **`separador` seguro:** usar `·` (U+00B7) como no padrão; não usar emojis/setas em texto que vá pro PDF.

---

## File Structure

**Backend**
- `scripts/init-meta-prod.sql` — +2 colunas em `CREATE TABLE empresas`.
- `README.md` — bloco "Deltas de schema pendentes": verify query + `ALTER TABLE`.
- `backend/middleware/auth.py` — `get_current_user` traz `company_endereco` / `company_cnpj` (branch normal + branch externo).
- `backend/routes/empresas.py` — `EmpresaInput` / `EmpresaUpdate` + SELECTs (`listar`, `detalhe`) + INSERT + UPDATE.
- `backend/tests/conftest.py` — `hard_delete_empresa(id)`.
- `backend/tests/test_empresas_endereco_cnpj.py` — **novo**.

**Frontend — infra do relatório**
- `frontend/src/lib/resumoFiltros.js` — **novo**, função pura extraída do painel.
- `frontend/src/lib/relatorio/tema-relatorio.css` — **novo**, paleta + regras `@page` / `@media print`.
- `frontend/src/lib/relatorio/RelatorioCabecalho.svelte` — **novo**.
- `frontend/src/lib/relatorio/RelatorioRodape.svelte` — **novo**.
- `frontend/src/routes/relatorio/painel/[slug]/+page.svelte` — **novo**, a rota de relatório.
- `frontend/src/routes/+layout.svelte` — carve-out (renderiza `<slot/>` puro pra `/relatorio/`) + `empresaAtiva` ganha `endereco`/`cnpj`.

**Frontend — componentes e telas existentes**
- `frontend/src/lib/components/ChartPanel.svelte` — `dispatch('pronto')`.
- `frontend/src/lib/components/MapPanel.svelte` — `dispatch('pronto')` + prop `temaForcado`.
- `frontend/src/lib/components/DataTable.svelte` — prop `modoRelatorio`; props `painelSlug`/`indicadorId`/`filtrosQuery`; botão PDF abre a rota.
- `frontend/src/lib/components/DynamicTable.svelte` — idem.
- `frontend/src/lib/exportTable.js` — remove tudo de jsPDF.
- `frontend/package.json` — remove `jspdf`, `jspdf-autotable`.
- `frontend/src/routes/painel/[slug]/+page.svelte` — botão "Imprimir" + passa props pras tabelas + usa `resumoFiltros.js`.
- `frontend/src/routes/configuracoes/empresas/nova/+page.svelte` e `[id]/+page.svelte` — campos Endereço / CNPJ.

---

## Task 1: Backend — colunas `endereco` e `cnpj` em `empresas`

**Files:**
- Modify: `scripts/init-meta-prod.sql` (bloco `CREATE TABLE empresas`, ~linha 16-30)
- Modify: `README.md` (bloco "Deltas de schema pendentes", ~linha 124-127 e ~linha 264)
- Modify: `backend/middleware/auth.py:39-58` e `:67-81`
- Modify: `backend/routes/empresas.py` (`EmpresaInput` :21-30, `EmpresaUpdate` :33-43, `listar_empresas` :62-64, `buscar_empresa` :95-98, `criar_empresa` :123-128, `atualizar_empresa` :145-157)
- Modify: `backend/tests/conftest.py` (adicionar helper)
- Test: `backend/tests/test_empresas_endereco_cnpj.py` (novo)

**Interfaces:**
- Produces:
  - `GET /api/empresas/{id}` e `GET /api/empresas/` retornam `endereco: str | None`, `cnpj: str | None`.
  - `POST /api/empresas/` e `PATCH /api/empresas/{id}` aceitam `endereco`, `cnpj` no corpo.
  - `GET /api/auth/me` retorna `company_endereco: str | None`, `company_cnpj: str | None`.
  - `conftest.hard_delete_empresa(empresa_id: int) -> None` — `DELETE` real (apaga `usuario_empresas` antes).

- [ ] **Step 1: Aplicar o schema no banco de dev**

Colunas novas precisam existir antes dos testes rodarem:

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco TEXT; ALTER TABLE empresas ADD COLUMN IF NOT EXISTS cnpj VARCHAR(20);"
```

Confirmar:

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "\d empresas" | grep -E "endereco|cnpj"
```

Esperado: as duas linhas aparecem.

- [ ] **Step 2: Adicionar o helper de limpeza no `conftest.py`**

Em `backend/tests/conftest.py`, depois de `hard_delete_variavel` (~linha 56):

```python
def hard_delete_empresa(empresa_id: int):
    """Remove de verdade uma empresa criada pra teste. DELETE /api/empresas/{id}
    é soft-delete (ativo=false) e deixaria lixo permanente no banco de dev."""
    async def _exec():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM usuario_empresas WHERE empresa_id = $1", empresa_id)
            await conn.execute("DELETE FROM empresas WHERE id = $1", empresa_id)
        finally:
            await conn.close()
    asyncio.run(_exec())
```

- [ ] **Step 3: Escrever o teste (falhando)**

Criar `backend/tests/test_empresas_endereco_cnpj.py`:

```python
import asyncio
import pytest
from conftest import _connect_meta, hard_delete_empresa


@pytest.fixture
def empresa_temp():
    """Insere uma empresa direto no banco — o POST da API tenta conectar no
    banco de dados da empresa, o que não dá pra garantir em teste — e limpa no fim."""
    async def _criar():
        conn = await _connect_meta()
        try:
            row = await conn.fetchrow("""
                INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo)
                VALUES ('teste-endereco-rel', 'Teste Endereco Rel', 'x', 5432, 'x', 'x', 'x', true)
                RETURNING id
            """)
            return row["id"]
        finally:
            await conn.close()
    empresa_id = asyncio.run(_criar())
    yield empresa_id
    hard_delete_empresa(empresa_id)


PAYLOAD_BASE = {
    "slug": "teste-endereco-rel", "nome": "Teste Endereco Rel",
    "db_host": "x", "db_port": 5432, "db_name": "x", "db_user": "x", "ativo": True,
}


def test_patch_e_get_devolvem_endereco_cnpj(client, auth_token, empresa_temp):
    h = {"Authorization": f"Bearer {auth_token}"}
    r = client.patch(f"/api/empresas/{empresa_temp}", headers=h, json={
        **PAYLOAD_BASE,
        "endereco": "Rua Teste, 123 - Centro - CEP 00000-000",
        "cnpj": "12.345.678/0001-90",
    })
    assert r.status_code == 200

    body = client.get(f"/api/empresas/{empresa_temp}", headers=h).json()
    assert body["endereco"] == "Rua Teste, 123 - Centro - CEP 00000-000"
    assert body["cnpj"] == "12.345.678/0001-90"


def test_listar_empresas_inclui_campos(client, auth_token, empresa_temp):
    h = {"Authorization": f"Bearer {auth_token}"}
    client.patch(f"/api/empresas/{empresa_temp}", headers=h,
                 json={**PAYLOAD_BASE, "endereco": "Av X", "cnpj": "00"})
    lista = client.get("/api/empresas/", headers=h).json()
    alvo = next(e for e in lista if e["id"] == empresa_temp)
    assert alvo["endereco"] == "Av X"
    assert alvo["cnpj"] == "00"


def test_me_inclui_company_endereco_cnpj(client, auth_token):
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"}).json()
    assert "company_endereco" in me
    assert "company_cnpj" in me
```

- [ ] **Step 4: Rodar o teste e ver falhar**

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_endereco_cnpj.py -v`
Esperado: FAIL — `test_patch_e_get...` e `test_listar...` com `KeyError: 'endereco'`; `test_me...` com `assert 'company_endereco' in me` falso.

- [ ] **Step 5: `middleware/auth.py` — trazer os campos**

No branch externo (`SELECT id, nome, slug, url_impressao_base FROM empresas ...`, ~linha 40):

```python
        empresa_rows = await query_meta(
            "SELECT id, nome, slug, url_impressao_base, endereco, cnpj FROM empresas WHERE id = $1 AND ativo = true",
            empresa_id
        )
```

E no dict retornado desse branch (~linha 47-58), adicionar:

```python
            "company_endereco": empresa["endereco"],
            "company_cnpj": empresa["cnpj"],
```

No SELECT do branch normal (~linha 67-76):

```python
    rows = await query_meta("""
        SELECT u.id, u.nome, u.role, u.tema,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name,
               e.url_impressao_base, e.endereco AS company_endereco, e.cnpj AS company_cnpj,
               ue.codigo_usuario_externo
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, user_id, empresa_id)
```

- [ ] **Step 6: `routes/empresas.py` — models**

`EmpresaInput` (~linha 21-30): adicionar antes do fim da classe:

```python
    endereco: str | None = None
    cnpj: str | None = None
```

`EmpresaUpdate` (~linha 33-43): adicionar:

```python
    endereco: str | None = None
    cnpj: str | None = None
```

- [ ] **Step 7: `routes/empresas.py` — SELECTs**

`listar_empresas` (~linha 62-64):

```python
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, ativo, criado_em, endereco, cnpj FROM empresas ORDER BY nome"
    )
```

`buscar_empresa` (~linha 95-98):

```python
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, db_user, ativo, criado_em, sso_query_acesso, url_impressao_base, endereco, cnpj FROM empresas WHERE id = $1",
        id
    )
```

- [ ] **Step 8: `routes/empresas.py` — INSERT e UPDATE**

`criar_empresa` (~linha 123-128):

```python
        rows = await query_meta("""
            INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo, url_impressao_base, endereco, cnpj)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo, body.url_impressao_base,
            body.endereco, body.cnpj)
```

`atualizar_empresa` (~linha 145-157) — o `id` passa de `$11` pra `$13`:

```python
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6,
                db_pass=COALESCE($7, db_pass),
                ativo=$8,
                sso_query_acesso=$9,
                url_impressao_base=$10,
                endereco=$11,
                cnpj=$12
            WHERE id=$13
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo,
            body.sso_query_acesso, body.url_impressao_base,
            body.endereco, body.cnpj, id)
```

- [ ] **Step 9: Rodar os testes e ver passar**

Run: `docker restart datahub_backend && sleep 3 && docker exec datahub_backend python -m pytest tests/test_empresas_endereco_cnpj.py -v`
Esperado: 3 PASS.

- [ ] **Step 10: Rodar a suíte inteira (não quebrou nada)**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Esperado: tudo verde (mesmo número de testes de antes + 3).

- [ ] **Step 11: `init-meta-prod.sql` + README**

Em `scripts/init-meta-prod.sql`, no `CREATE TABLE empresas` (depois de `url_impressao_base TEXT`):

```sql
    url_impressao_base TEXT,
    endereco     TEXT,
    cnpj         VARCHAR(20)
```

(ajustar a vírgula: a linha `url_impressao_base TEXT` vira `url_impressao_base TEXT,`)

Em `README.md`, na query de verificação de `empresas` (~linha 124-126):

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'empresas'
  AND column_name IN ('sso_api_key_hash', 'sso_query_acesso', 'url_impressao_base', 'endereco', 'cnpj');
```

E no fim do bloco de `ALTER TABLE` (depois da linha `ALTER TABLE queries ADD COLUMN kpi_valor_primeiro ...`, ~linha 265):

```sql
-- 2026-09-08 — endereço e CNPJ da empresa pro cabeçalho dos relatórios impressos
ALTER TABLE empresas ADD COLUMN endereco TEXT;
ALTER TABLE empresas ADD COLUMN cnpj VARCHAR(20);
```

- [ ] **Step 12: Commit**

```bash
git add scripts/init-meta-prod.sql README.md backend/middleware/auth.py backend/routes/empresas.py backend/tests/conftest.py backend/tests/test_empresas_endereco_cnpj.py
git commit -m "$(cat <<'EOF'
feat: endereco e cnpj em empresas (cabecalho de relatorio)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 2: Frontend — campos Endereço / CNPJ na config de empresa

**Files:**
- Modify: `frontend/src/routes/configuracoes/empresas/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`

**Interfaces:**
- Consumes: `POST /api/empresas/` e `PATCH /api/empresas/{id}` aceitando `endereco`, `cnpj` (Task 1).
- Produces: nada pra tarefas seguintes (só UI).

- [ ] **Step 1: `nova/+page.svelte` — estado e payload**

Adicionar as vars (junto de `url_impressao_base`, ~linha 12):

```js
  let endereco = '';
  let cnpj     = '';
```

No `salvar()`, no objeto passado pra `api.criarEmpresa(...)` (~linha 90):

```js
      const empresa = await api.criarEmpresa({ slug, nome, db_host, db_port, db_name, db_user, db_pass, url_impressao_base: url_impressao_base || null, endereco: endereco || null, cnpj: cnpj || null });
```

- [ ] **Step 2: `nova/+page.svelte` — inputs**

Na `<section>` "Dados da Empresa", depois do label de "URL base de impressão" (~linha 135):

```svelte
      <label>
        Endereço (aparece no cabeçalho dos relatórios)
        <input bind:value={endereco} placeholder="Rua Principal, 1 - Centro - CEP 00000-000 - Cidade - UF" />
      </label>
      <label>
        CNPJ
        <input bind:value={cnpj} placeholder="00.000.000/0001-00" />
      </label>
```

- [ ] **Step 3: `[id]/+page.svelte` — payload**

No `salvar()`, no objeto `payload` (~linha 115-125):

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
        endereco: empresa.endereco ?? null,
        cnpj:     empresa.cnpj ?? null,
      };
```

- [ ] **Step 4: `[id]/+page.svelte` — inputs**

Depois do label "URL base de impressão (opcional)" (~linha 183):

```svelte
        <label>
          Endereço (aparece no cabeçalho dos relatórios)
          <input bind:value={empresa.endereco} placeholder="Rua Principal, 1 - Centro - CEP 00000-000 - Cidade - UF" />
        </label>
        <label>
          CNPJ
          <input bind:value={empresa.cnpj} placeholder="00.000.000/0001-00" />
        </label>
```

(o `GET /api/empresas/{id}` já devolve `endereco`/`cnpj` depois da Task 1, então `empresa.endereco` chega preenchido)

- [ ] **Step 5: Restart e checar**

Run: `docker restart datahub_frontend && cd frontend && npm run check`
Esperado: `npm run check` sem erros novos.

- [ ] **Step 6: Verificação manual (Playwright ou navegador)**

Login admin → `/configuracoes/empresas` → editar `alpha` → preencher Endereço = `Rua Teste Rel, 1 - Centro` e CNPJ = `11.111.111/0001-11` → Salvar → reabrir a edição → os dois campos vêm preenchidos.

Reverter depois (limpar os campos e salvar) pra não sujar o seed — ou deixar, já que `alpha` é seed de dev.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/configuracoes/empresas/
git commit -m "$(cat <<'EOF'
feat: campos endereco e cnpj na tela de config de empresa

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 3: Frontend — extrair `resumoFiltros` pra módulo compartilhado

**Files:**
- Create: `frontend/src/lib/resumoFiltros.js`
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte:24-51` e `:216-222`

**Interfaces:**
- Produces:
  - `resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel = {}) -> Array<{nome: string, valor: string}>`
  - `fmtData(val: string) -> string` (`'2026-09-08'` → `'08/09/2026'`)

- [ ] **Step 1: Criar o módulo**

`frontend/src/lib/resumoFiltros.js`:

```js
// YYYY-MM-DD → DD/MM/YYYY
export function fmtData(val) {
  if (!val || val.length !== 10) return val ?? '';
  const [y, m, d] = val.split('-');
  return `${d}/${m}/${y}`;
}

// Resumo legível dos filtros ativos de um painel: [{nome, valor}].
// Extraído de /painel/[slug]/+page.svelte pra ser reusado pela rota de relatório.
export function resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel = {}) {
  return variaveis.flatMap(v => {
    if (v.tipo === 'date_range') {
      const ini = filtrosAtivos[v.slug + '_inicio'];
      const fim = filtrosAtivos[v.slug + '_fim'];
      if (!ini && !fim) return [];
      return [{ nome: v.nome, valor: `${fmtData(ini) || '—'} até ${fmtData(fim) || '—'}` }];
    }
    const val = filtrosAtivos[v.slug];
    if (!val) return [];

    if (v.tipo === 'select' || v.tipo === 'multiselect') {
      const opcoes = opcoesPorVariavel[v.slug] || [];
      const labels = String(val).split(',').map(id => {
        const opt = opcoes.find(o => String(o.valor) === id);
        return opt ? opt.label : id;
      });
      return [{ nome: v.nome, valor: labels.join(', ') }];
    }

    return [{ nome: v.nome, valor: String(val) }];
  });
}
```

- [ ] **Step 2: Usar no painel — import + remover a duplicata**

Em `frontend/src/routes/painel/[slug]/+page.svelte`:

Adicionar o import (junto dos outros, ~linha 4):

```js
  import { resumoFiltros } from '$lib/resumoFiltros.js';
```

Remover a função local `fmtData` (linhas ~23-28) e o bloco reativo `$: resumoFiltros = variaveis.flatMap(...)` inteiro (linhas ~30-51), substituindo por:

```js
  $: resumoFiltrosLista = resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel);
```

- [ ] **Step 3: Atualizar o template**

Nas linhas ~215-222, trocar as duas referências:

```svelte
        <div class="filtros-chips">
          {#if resumoFiltrosLista.length > 0}
            {#each resumoFiltrosLista as f}
              <span class="chip">
                <span class="chip-nome">{f.nome}:</span>
                <span class="chip-val">{f.valor}</span>
              </span>
            {/each}
          {:else}
            <span class="sem-filtro">Sem filtros ativos</span>
          {/if}
        </div>
```

- [ ] **Step 4: Restart + check**

Run: `docker restart datahub_frontend && cd frontend && npm run check`
Esperado: sem erros. Nenhuma referência solta a `fmtData` local ou `resumoFiltros` como variável.

- [ ] **Step 5: Verificação manual**

Login → abrir painel `lanc_fichas` → abrir Filtros → escolher um valor no multiselect "Fazenda" e um período → Aplicar → os chips de resumo aparecem iguais a antes (nome + label, datas em DD/MM/YYYY).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/resumoFiltros.js frontend/src/routes/painel/
git commit -m "$(cat <<'EOF'
refactor: extrai resumoFiltros do painel pra $lib/resumoFiltros.js

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 4: Frontend — tema do relatório, cabeçalho/rodapé e rota base

**Files:**
- Create: `frontend/src/lib/relatorio/tema-relatorio.css`
- Create: `frontend/src/lib/relatorio/RelatorioCabecalho.svelte`
- Create: `frontend/src/lib/relatorio/RelatorioRodape.svelte`
- Create: `frontend/src/routes/relatorio/painel/[slug]/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte:99-106` (empresaAtiva) e `:159-161` (carve-out)

**Interfaces:**
- Consumes: `resumoFiltros` (Task 3); `api.me` → `{ company_name, company_endereco, company_cnpj, empresa_id }` (Task 1); `api.buscarPainelPorSlug`, `api.variaveisPainel`, `api.executarFonteVariavel`, `api.renderizarPainel` (já existem).
- Produces:
  - `RelatorioCabecalho` props: `titulo`, `subtitulo`, `empresaNome`, `empresaEndereco`, `empresaCnpj`, `empresaLogoUrl`, `filtros: Array<{nome,valor}>`.
  - `RelatorioRodape` — sem props.
  - Rota `/relatorio/painel/<slug>?<filtros>&indicador=<id>` — renderiza cabeçalho + corpo + rodapé; nesta task o corpo é um placeholder (lista de títulos). Adiciona `relatorio-tema` no `<html>` no `onMount`, remove no `onDestroy`.
  - `+layout.svelte`: rotas sob `/relatorio/` renderizam `<slot/>` puro (sem shell), mantendo o guard de auth.

- [ ] **Step 1: `tema-relatorio.css`**

`frontend/src/lib/relatorio/tema-relatorio.css`:

```css
/* Tema visual dos relatórios impressos — paleta verde-clara do padrão
   (docs/superpowers/specs/2026-09-08-impressao-relatorio-painel-design.md),
   independente do tema do app. Ativado pela classe `relatorio-tema` no <html>
   (a rota /relatorio/painel/[slug] adiciona no onMount e remove no onDestroy).
   Escopado em :root pra que o ChartPanel — que lê as CSS vars via
   getComputedStyle(document.documentElement) — pegue a paleta clara. */

:root.relatorio-tema {
  --bg:            #F4F6F2;
  --surface:       #FFFFFF;
  --surface2:      #E9F3EC;
  --border:        #E3E8E1;
  --text:          #2B2B2B;
  --muted:         #8A968A;
  --accent:        #2E5E3E;
  --accent-blue:   #2E5E3E;
  --accent-green:  #4CAF50;
  --accent-orange: #E8A33D;
  --danger:        #C62828;

  --rel-verde-escuro: #1F3D2B;
  --rel-verde:        #2E5E3E;
  --rel-verde-suave:  #BFE3C6;

  background: var(--bg);
  color: var(--text);
}

.relatorio-tema body { background: var(--bg); margin: 0; }

.relatorio-pagina {
  max-width: 210mm;
  margin: 0 auto;
  padding: 150px 16mm 60px;   /* topo/base livres pro cabeçalho/rodapé fixos */
  background: var(--surface);
  min-height: 100vh;
  box-sizing: border-box;
}

@media screen {
  .relatorio-tema body { padding: 24px 0; }
  .relatorio-pagina { box-shadow: 0 2px 24px rgba(0,0,0,.12); border-radius: 4px; }
}

@media screen and (max-width: 820px) {
  .relatorio-pagina { padding: 150px 12px 60px; }
}

@media print {
  @page { size: A4; margin: 12mm; }

  .no-print { display: none !important; }

  html, body, .relatorio-tema body { background: #fff !important; }

  .relatorio-pagina {
    max-width: none; margin: 0; box-shadow: none; border-radius: 0;
    padding: 132px 0 52px;
  }

  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }

  thead { display: table-header-group; }
}
```

- [ ] **Step 2: `RelatorioRodape.svelte`**

`frontend/src/lib/relatorio/RelatorioRodape.svelte`:

```svelte
<script>
  const geradoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short',
  }).format(new Date());
</script>

<footer class="rr">
  <span>DataHub · GPA Analytics</span>
  <span>Relatório gerado eletronicamente · {geradoEm}</span>
</footer>

<style>
  .rr {
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 10;
    display: flex; justify-content: space-between; gap: 12px;
    padding: 6px 16mm;
    border-top: 1px solid #E3E8E1;
    background: #F4F6F2;
    font-size: 9px; color: #8A968A;
  }
  @media print { .rr { background: #fff; padding: 6px 12mm; } }
</style>
```

- [ ] **Step 3: `RelatorioCabecalho.svelte`**

`frontend/src/lib/relatorio/RelatorioCabecalho.svelte`:

```svelte
<script>
  export let titulo = '';
  export let subtitulo = '';
  export let empresaNome = '';
  export let empresaEndereco = '';
  export let empresaCnpj = '';
  export let empresaLogoUrl = null;
  export let filtros = [];   // [{nome, valor}]

  const emitidoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short',
  }).format(new Date());
</script>

<header class="rc">
  <div class="rc-faixa">
    <svg class="rc-arcos" viewBox="0 0 800 150" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <circle cx="720" cy="10"  r="120" fill="#ffffff" opacity="0.04" />
      <circle cx="780" cy="95"  r="95"  fill="#ffffff" opacity="0.05" />
      <circle cx="610" cy="150" r="70"  fill="#ffffff" opacity="0.03" />
    </svg>

    <div class="rc-logo-wrap">
      {#if empresaLogoUrl}
        <img class="rc-logo" src={empresaLogoUrl} alt="" on:error={(e) => (e.target.style.display = 'none')} />
      {/if}
    </div>

    <div class="rc-centro">
      {#if subtitulo}<span class="rc-subtitulo">{subtitulo}</span>{/if}
      <h1 class="rc-titulo">{titulo}</h1>
    </div>

    <div class="rc-empresa">
      <span class="rc-empresa-nome">{empresaNome}</span>
      {#if empresaEndereco}<span class="rc-meta">{empresaEndereco}</span>{/if}
      {#if empresaCnpj}<span class="rc-meta">CNPJ: {empresaCnpj}</span>{/if}
      <span class="rc-meta">Emitido em {emitidoEm}</span>
    </div>
  </div>

  {#if filtros.length}
    <div class="rc-filtros">
      {#each filtros as f}
        <span class="rc-chip"><strong>{f.nome}:</strong> {f.valor}</span>
      {/each}
    </div>
  {/if}
</header>

<style>
  .rc {
    position: fixed; top: 0; left: 0; right: 0; z-index: 10;
    background: #F4F6F2;
  }
  .rc-faixa {
    position: relative; overflow: hidden;
    display: grid; grid-template-columns: auto 1fr auto; align-items: center;
    gap: 18px; padding: 14px 16mm;
    background: linear-gradient(120deg, #1F3D2B, #2E5E3E);
    color: #fff;
  }
  .rc-arcos { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .rc-logo-wrap {
    width: 68px; height: 68px; border-radius: 50%; background: #fff;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0; z-index: 1;
  }
  .rc-logo { width: 54px; height: 54px; object-fit: contain; }
  .rc-centro { z-index: 1; min-width: 0; }
  .rc-subtitulo {
    display: block; font-size: 10px; font-weight: 700; letter-spacing: .14em; color: #BFE3C6;
  }
  .rc-titulo { margin: 2px 0 0; font-size: 21px; font-weight: 700; line-height: 1.15; color: #fff; }
  .rc-empresa { z-index: 1; text-align: right; display: flex; flex-direction: column; gap: 1px; }
  .rc-empresa-nome { font-size: 12px; font-weight: 700; }
  .rc-meta { font-size: 9.5px; color: #DDE8DD; }
  .rc-filtros {
    display: flex; flex-wrap: wrap; gap: 6px; padding: 7px 16mm;
    background: #F4F6F2; border-bottom: 1px solid #BFE3C6;
  }
  .rc-chip {
    font-size: 10px; color: #2B2B2B; background: #E9F3EC;
    border: 1px solid #CFE6D6; border-radius: 999px; padding: 2px 8px;
  }
  .rc-chip strong { color: #8A968A; font-weight: 700; }

  @media print { .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
</style>
```

- [ ] **Step 4: `+layout.svelte` — carve-out da rota de relatório**

Em `frontend/src/routes/+layout.svelte`, trocar o topo do bloco de markup (~linha 159):

```svelte
{#if PUBLIC_ROUTES.includes($page.url.pathname)}
  <slot />
{:else if $page.url.pathname.startsWith('/relatorio/')}
  <slot />
{:else}
  <div class="shell">
```

(o `{:else}` que já existe fecha o `shell` — só a condição do meio é nova; o `{/if}` final continua igual)

O `onMount` de auth (~linha 87-113) **não muda** — `/relatorio/...` não está em `PUBLIC_ROUTES`, então o guard de token continua rodando pra essa rota.

- [ ] **Step 5: `+layout.svelte` — empresaAtiva com endereco/cnpj**

No `onMount` de auth, no `empresaAtiva.set({...})` (~linha 100-105):

```js
          empresaAtiva.set({
            id: me.empresa_id, slug: me.company_slug,
            nome: me.company_name,
            endereco: me.company_endereco ?? null,
            cnpj: me.company_cnpj ?? null,
            logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
            url_impressao_base: me.url_impressao_base ?? null
          });
```

- [ ] **Step 6: Rota de relatório — versão base (corpo placeholder)**

`frontend/src/routes/relatorio/painel/[slug]/+page.svelte`:

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import { api, assetUrl } from '$lib/api.js';
  import { resumoFiltros } from '$lib/resumoFiltros.js';
  import RelatorioCabecalho from '$lib/relatorio/RelatorioCabecalho.svelte';
  import RelatorioRodape from '$lib/relatorio/RelatorioRodape.svelte';
  import '$lib/relatorio/tema-relatorio.css';

  const params = $page.url.searchParams;
  const slug = $page.params.slug;
  const idIndicador = params.get('indicador');

  let carregando = true;
  let erro = null;
  let painel = null;
  let indicadores = [];
  let indicadorUnico = null;
  let filtrosResumo = [];
  let empresa = { nome: '', endereco: '', cnpj: '', logo_url: null };

  function filtrosDaURL() {
    const f = {};
    for (const [k, v] of params.entries()) {
      if (k === 'indicador') continue;
      f[k] = v;
    }
    return f;
  }

  onMount(async () => {
    document.documentElement.classList.add('relatorio-tema');
    document.documentElement.removeAttribute('data-theme');
    try {
      const me = await api.me();
      empresa = {
        nome: me.company_name ?? '',
        endereco: me.company_endereco ?? '',
        cnpj: me.company_cnpj ?? '',
        logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
      };

      painel = await api.buscarPainelPorSlug(slug);
      const variaveis = await api.variaveisPainel(painel.id);
      const filtros = filtrosDaURL();

      const opcoesPorVariavel = {};
      await Promise.all(
        variaveis
          .filter(v => v.tipo === 'select' || v.tipo === 'multiselect')
          .map(async v => {
            try { opcoesPorVariavel[v.slug] = await api.executarFonteVariavel(v.variavel_id || v.id); }
            catch { opcoesPorVariavel[v.slug] = []; }
          })
      );
      filtrosResumo = resumoFiltros(variaveis, filtros, opcoesPorVariavel);

      const resultado = await api.renderizarPainel(painel.id, filtros);
      indicadores = resultado.indicadores ?? [];
      if (idIndicador) {
        indicadorUnico = indicadores.find(i => String(i.id) === String(idIndicador)) ?? null;
      }
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  onDestroy(() => {
    document.documentElement.classList.remove('relatorio-tema');
  });

  $: tituloRelatorio = indicadorUnico
    ? (indicadorUnico.titulo || indicadorUnico.query_slug)
    : (painel?.nome ?? 'Relatório');
  $: subtituloRelatorio = idIndicador ? 'RELAÇÃO DE DADOS' : 'RELATÓRIO DE INDICADORES';
  $: lista = indicadorUnico ? [indicadorUnico] : indicadores;
</script>

<svelte:head><title>{tituloRelatorio} — Relatório</title></svelte:head>

<RelatorioCabecalho
  titulo={tituloRelatorio}
  subtitulo={subtituloRelatorio}
  empresaNome={empresa.nome}
  empresaEndereco={empresa.endereco}
  empresaCnpj={empresa.cnpj}
  empresaLogoUrl={empresa.logo_url}
  filtros={filtrosResumo}
/>

<div class="relatorio-pagina">
  {#if carregando}
    <p>Carregando relatório…</p>
  {:else if erro}
    <p style="color:#C62828">{erro}</p>
  {:else}
    <!-- placeholder — Task 5 substitui pelo grid real -->
    <ul>
      {#each lista as ind}
        <li>{ind.titulo || ind.query_slug} — {ind.query_tipo}{#if ind.erro} (erro: {ind.erro}){/if}</li>
      {/each}
    </ul>
  {/if}
</div>

<RelatorioRodape />
```

- [ ] **Step 7: Restart + check**

Run: `docker restart datahub_frontend && cd frontend && npm run check`
Esperado: sem erros.

- [ ] **Step 8: Verificação manual (Playwright)**

Login admin (empresa `alpha` — garantir que tem endereço preenchido da Task 2, senão preencher) → navegar pra `http://localhost:3000/relatorio/painel/lanc_fichas` numa aba → deve aparecer:
- Sem sidebar / sem topbar do app.
- Faixa verde no topo com círculo do logo, subtítulo `RELATÓRIO DE INDICADORES`, título `Lançamento de Fichas`, nome + endereço da empresa à direita, "Emitido em ...".
- Corpo: lista com os títulos dos indicadores e seus tipos.
- Rodapé fixo embaixo com "DataHub · GPA Analytics".

Tirar screenshot.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/relatorio/ frontend/src/routes/relatorio/ frontend/src/routes/+layout.svelte
git commit -m "$(cat <<'EOF'
feat: rota de relatorio com cabecalho/rodape padrao (corpo placeholder)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 5: Frontend — corpo do relatório (grid real) + prontidão + modo indicador único

**Files:**
- Modify: `frontend/src/lib/components/ChartPanel.svelte:138-145`
- Modify: `frontend/src/lib/components/MapPanel.svelte` (`onMount` :23-32, `aplicarTileLayer` :41-46, novo prop)
- Modify: `frontend/src/lib/components/DataTable.svelte` (novo prop `modoRelatorio` + render)
- Modify: `frontend/src/lib/components/DynamicTable.svelte` (novo prop `modoRelatorio` + render)
- Modify: `frontend/src/routes/relatorio/painel/[slug]/+page.svelte` (corpo real, toolbar, prontidão)

**Interfaces:**
- Consumes: componentes de indicador existentes; `indicadores` do `renderizarPainel` com campos `id, coluna, col_span, linha, row_span, titulo, query_slug, query_tipo, query_id, dados, erro, kpi_*, chart_*, mapa_camada, agrupamentos, agregacoes` (já retornados).
- Produces:
  - `ChartPanel` emite `pronto` após o primeiro `setOption`.
  - `MapPanel` emite `pronto` quando os tiles carregam (ou timeout); aceita `temaForcado: 'claro'|'escuro'|null`.
  - `DataTable` / `DynamicTable` aceitam `modoRelatorio: boolean` — sem paginação/controles, células com wrap, árvore toda expandida (dynamic).
  - Rota: botão "Imprimir / Salvar PDF" habilita quando todos os `chart_*`/`map` emitiram `pronto` (com fallback de 12s); `@page landscape` quando indicador único é tabela com > 8 colunas.

- [ ] **Step 1: `ChartPanel` emite `pronto`**

`createEventDispatcher` já está importado e `dispatch` já existe (linha 16). No `onMount` (~linha 138-141), depois do `if (dados.length) chart.setOption(...)`:

```js
  onMount(() => {
    chart = echarts.init(container, null, { renderer: 'svg' });
    chart.on('click', onClickGrafico);
    if (dados.length) chart.setOption(buildOption(tipo, dados));
    dispatch('pronto');
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(container);
    return () => ro.disconnect();
  });
```

- [ ] **Step 2: `MapPanel` — prop `temaForcado` + evento `pronto`**

No `<script>` (~linha 1-6):

```js
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { usuario } from '$lib/stores/auth.js';

  export let pontos = [];
  export let camada = 'padrao';
  export let temaForcado = null;   // 'claro' | 'escuro' | null — força a camada de tiles no relatório

  const dispatch = createEventDispatcher();
```

Trocar as leituras de `$usuario?.tema` por um helper. Adicionar depois das `const`:

```js
  $: temaEfetivo = temaForcado ?? $usuario?.tema ?? 'escuro';
```

No `onMount` (~linha 30): `aplicarTileLayer(L, temaEfetivo);`
No bloco reativo de tema (~linha 34): trocar `$usuario.tema` por `temaEfetivo` nas 2 ocorrências.
Em `alternarCamada` (~linha 50): `aplicarTileLayer(leafletRef, temaEfetivo);`

Em `aplicarTileLayer` (~linha 41-46):

```js
  function aplicarTileLayer(L, tema) {
    if (tileLayer) tileLayer.remove();
    const url = camadaAtiva === 'satelite' ? TILE_URLS.satelite : (TILE_URLS[tema] ?? TILE_URLS.escuro);
    tileLayer = L.tileLayer(url, { maxZoom: 19 }).addTo(map);
    tileLayer.once('load', () => dispatch('pronto'));
    temaAtual = tema;
  }
```

No `onMount`, no fim do callback (depois de `renderPontos(L)`), garantir prontidão mesmo se `load` não disparar (poucos pontos / erro de tile):

```js
    map.whenReady(() => setTimeout(() => dispatch('pronto'), 2500));
```

- [ ] **Step 3: `DataTable` — `modoRelatorio`**

No `<script>`, junto dos outros `export let` (~linha 16):

```js
  export let modoRelatorio = false;
  export let painelSlug   = null;   // usados só fora do modo relatório (Task 6)
  export let indicadorId  = null;
  export let filtrosQuery = '';
```

Adicionar a lista efetiva de linhas (~depois da linha 45):

```js
  $: linhasVisiveis = modoRelatorio ? dados : dadosPaginados;
```

No `<tbody>` e no `.cards-mobile`, trocar `{#each dadosPaginados as row}` por `{#each linhasVisiveis as row}` (2 lugares).

Na `.table-wrap`, adicionar classe condicional:

```svelte
<div class="table-wrap" class:modo-relatorio={modoRelatorio}>
```

Envolver a `<div class="pagination">` inteira:

```svelte
  {#if !modoRelatorio}
  <div class="pagination">
    ... (conteúdo atual intacto) ...
  </div>
  {/if}
```

No `<style>`, adicionar:

```css
.modo-relatorio { overflow: visible; }
.modo-relatorio table { font-size: 11px; }
.modo-relatorio th, .modo-relatorio td { white-space: normal; overflow-wrap: anywhere; padding: 6px 8px; }
.modo-relatorio .cards-mobile { display: none; }
```

- [ ] **Step 4: `DynamicTable` — `modoRelatorio`**

No `<script>` (~linha 17):

```js
  export let modoRelatorio = false;
  export let painelSlug   = null;
  export let indicadorId  = null;
  export let filtrosQuery = '';
```

Depois da declaração de `expandidos` (~linha 66-71):

```js
  // No relatório a árvore sai toda expandida — um "Set" que responde sempre true.
  $: expandidosEfetivo = modoRelatorio ? { has: () => true } : expandidos;
```

Nos dois `<GrupoLinha ... {expandidos} ...>` (linhas ~118-121 e ~126-129), trocar `{expandidos}` por `expandidos={expandidosEfetivo}`.

Envolver a `.export-bar`:

```svelte
  {#if !modoRelatorio}
  <div class="export-bar">
    ... (conteúdo atual intacto) ...
  </div>
  {/if}
```

Na `.table-wrap`: `<div class="table-wrap" class:modo-relatorio={modoRelatorio}>` e no `<style>`:

```css
.modo-relatorio { overflow: visible; }
.modo-relatorio table { font-size: 11px; }
.modo-relatorio th, .modo-relatorio td { white-space: normal; overflow-wrap: anywhere; padding: 6px 8px; }
.modo-relatorio .cards-mobile { display: none; }
```

- [ ] **Step 5: Rota — corpo real + toolbar + prontidão**

Substituir o `+page.svelte` da rota de relatório inteiro por:

```svelte
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { page } from '$app/stores';
  import { api, assetUrl } from '$lib/api.js';
  import { resumoFiltros } from '$lib/resumoFiltros.js';
  import RelatorioCabecalho from '$lib/relatorio/RelatorioCabecalho.svelte';
  import RelatorioRodape from '$lib/relatorio/RelatorioRodape.svelte';
  import KPICard      from '$lib/components/KPICard.svelte';
  import ChartPanel   from '$lib/components/ChartPanel.svelte';
  import DataTable    from '$lib/components/DataTable.svelte';
  import DynamicTable from '$lib/components/DynamicTable.svelte';
  import MapPanel     from '$lib/components/MapPanel.svelte';
  import '$lib/relatorio/tema-relatorio.css';

  const params = $page.url.searchParams;
  const slug = $page.params.slug;
  const idIndicador = params.get('indicador');

  let carregando = true;
  let erro = null;
  let painel = null;
  let indicadores = [];
  let indicadorUnico = null;
  let filtrosResumo = [];
  let empresa = { nome: '', endereco: '', cnpj: '', logo_url: null };

  let prontos = new Set();
  let pronto = false;

  function filtrosDaURL() {
    const f = {};
    for (const [k, v] of params.entries()) {
      if (k === 'indicador') continue;
      f[k] = v;
    }
    return f;
  }

  function marcarPronto(id) {
    prontos = new Set(prontos).add(id);
    verificarPronto();
  }

  async function verificarPronto() {
    if (idsAssincronos.every(id => prontos.has(id))) {
      try { await (document.fonts?.ready ?? Promise.resolve()); } catch {}
      await tick();
      pronto = true;
    }
  }

  onMount(async () => {
    document.documentElement.classList.add('relatorio-tema');
    document.documentElement.removeAttribute('data-theme');
    try {
      const me = await api.me();
      empresa = {
        nome: me.company_name ?? '',
        endereco: me.company_endereco ?? '',
        cnpj: me.company_cnpj ?? '',
        logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
      };

      painel = await api.buscarPainelPorSlug(slug);
      const variaveis = await api.variaveisPainel(painel.id);
      const filtros = filtrosDaURL();

      const opcoesPorVariavel = {};
      await Promise.all(
        variaveis
          .filter(v => v.tipo === 'select' || v.tipo === 'multiselect')
          .map(async v => {
            try { opcoesPorVariavel[v.slug] = await api.executarFonteVariavel(v.variavel_id || v.id); }
            catch { opcoesPorVariavel[v.slug] = []; }
          })
      );
      filtrosResumo = resumoFiltros(variaveis, filtros, opcoesPorVariavel);

      const resultado = await api.renderizarPainel(painel.id, filtros);
      indicadores = resultado.indicadores ?? [];
      if (idIndicador) {
        indicadorUnico = indicadores.find(i => String(i.id) === String(idIndicador)) ?? null;
      }
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }

    await tick();
    verificarPronto();                       // caso não haja chart/map nenhum
    setTimeout(() => { pronto = true; }, 12000);  // fallback: nunca trava o botão
  });

  onDestroy(() => {
    document.documentElement.classList.remove('relatorio-tema');
  });

  $: lista = indicadorUnico ? [indicadorUnico] : indicadores;
  $: idsAssincronos = lista
    .filter(i => i && (String(i.query_tipo).startsWith('chart_') || i.query_tipo === 'map') && !i.erro)
    .map(i => i.id);
  $: tituloRelatorio = indicadorUnico
    ? (indicadorUnico.titulo || indicadorUnico.query_slug)
    : (painel?.nome ?? 'Relatório');
  $: subtituloRelatorio = idIndicador ? 'RELAÇÃO DE DADOS' : 'RELATÓRIO DE INDICADORES';

  function nColunas(ind) {
    return ind?.dados?.[0] ? Object.keys(ind.dados[0]).length : 0;
  }
  $: paisagem = !!indicadorUnico
    && (indicadorUnico.query_tipo === 'table' || indicadorUnico.query_tipo === 'table_dynamic')
    && nColunas(indicadorUnico) > 8;
</script>

<svelte:head>
  <title>{tituloRelatorio} — Relatório</title>
  {#if paisagem}<style>@page { size: A4 landscape; }</style>{/if}
</svelte:head>

<div class="relatorio-toolbar no-print">
  <strong>{tituloRelatorio}</strong>
  <span class="espaco"></span>
  {#if !pronto}<span class="preparando">Preparando relatório…</span>{/if}
  <button disabled={!pronto} on:click={() => window.print()}>Imprimir / Salvar PDF</button>
</div>

<RelatorioCabecalho
  titulo={tituloRelatorio}
  subtitulo={subtituloRelatorio}
  empresaNome={empresa.nome}
  empresaEndereco={empresa.endereco}
  empresaCnpj={empresa.cnpj}
  empresaLogoUrl={empresa.logo_url}
  filtros={filtrosResumo}
/>

<div class="relatorio-pagina">
  {#if carregando}
    <p>Carregando relatório…</p>
  {:else if erro}
    <p class="rel-erro">{erro}</p>
  {:else if indicadorUnico}
    <div class="rel-unico">
      <div class="card-titulo">{indicadorUnico.titulo || indicadorUnico.query_slug}</div>
      {#if indicadorUnico.query_tipo === 'table'}
        <DataTable dados={indicadorUnico.dados} titulo={tituloRelatorio} modoRelatorio={true} />
      {:else if indicadorUnico.query_tipo === 'table_dynamic'}
        <DynamicTable
          dados={indicadorUnico.dados}
          titulo={tituloRelatorio}
          agrupamentos={indicadorUnico.agrupamentos ?? []}
          agregacoes={indicadorUnico.agregacoes ?? []}
          modoRelatorio={true}
        />
      {:else}
        <p class="rel-erro">Só tabelas têm relatório individual.</p>
      {/if}
    </div>
  {:else}
    <div class="painel-grid" style="grid-template-columns: repeat({painel.colunas}, 1fr)">
      {#each indicadores as ind}
        <div class="grid-item" style="grid-column: {ind.coluna} / span {ind.col_span}; grid-row: {ind.linha} / span {ind.row_span};">
          <div class="card-titulo">{ind.titulo || ind.query_slug}</div>

          {#if ind.erro}
            <p class="rel-erro">{ind.erro}</p>
          {:else if ind.query_tipo === 'kpi'}
            <KPICard
              dados={ind.dados?.[0]}
              corFonte={ind.kpi_cor_fonte}
              corFundo={ind.kpi_cor_fundo}
              imagemUrl={ind.kpi_imagem_habilitada ? assetUrl(`/api/queries/${ind.query_id}/kpi-imagem`) : null}
              imagemPosicao={ind.kpi_imagem_posicao}
              valorPrimeiro={ind.kpi_valor_primeiro}
              descricao={ind.descricao}
            />
          {:else if String(ind.query_tipo).startsWith('chart_')}
            <ChartPanel
              tipo={ind.query_tipo}
              dados={ind.dados}
              fonteTamanho={ind.chart_fonte_tamanho}
              truncarLabel={ind.chart_truncar_label}
              truncarTamanho={ind.chart_truncar_tamanho}
              mostrarValor={ind.chart_mostrar_valor}
              valorLabel={ind.chart_valor_label}
              on:pronto={() => marcarPronto(ind.id)}
            />
          {:else if ind.query_tipo === 'table'}
            <DataTable dados={ind.dados} titulo={ind.titulo || ind.query_slug} modoRelatorio={true} />
          {:else if ind.query_tipo === 'table_dynamic'}
            <DynamicTable
              dados={ind.dados}
              titulo={ind.titulo || ind.query_slug}
              agrupamentos={ind.agrupamentos ?? []}
              agregacoes={ind.agregacoes ?? []}
              modoRelatorio={true}
            />
          {:else if ind.query_tipo === 'map'}
            <MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} temaForcado="claro" on:pronto={() => marcarPronto(ind.id)} />
          {:else}
            <p class="rel-erro">Tipo "{ind.query_tipo}" não suportado no relatório.</p>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<RelatorioRodape />

<style>
  .relatorio-toolbar { }
  .relatorio-toolbar .espaco { flex: 1; }
  .relatorio-toolbar .preparando { font-size: 13px; opacity: .9; }

  .painel-grid { display: grid; gap: 14px; }
  .grid-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden; min-width: 0; break-inside: avoid;
  }
  .rel-unico { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .card-titulo {
    padding: 10px 14px 6px; font-size: 11px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border);
  }
  .rel-erro { color: #C62828; font-size: 12px; padding: 8px 12px; }

  @media screen and (max-width: 820px) {
    .painel-grid { grid-template-columns: 1fr !important; }
    .grid-item { grid-column: 1 / -1 !important; grid-row: auto !important; }
  }
  @media print {
    .painel-grid { gap: 10px; }
  }
</style>
```

(a `.relatorio-toolbar` base — cores/posição — já vem de `tema-relatorio.css`; aqui só o resto. Adicionar o bloco `.relatorio-toolbar` em `tema-relatorio.css` — próximo step.)

- [ ] **Step 6: `tema-relatorio.css` — estilo da toolbar**

Adicionar em `frontend/src/lib/relatorio/tema-relatorio.css`, antes do `@media print`:

```css
.relatorio-toolbar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 50;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  background: var(--rel-verde, #2E5E3E); color: #fff;
}
.relatorio-toolbar button {
  font: inherit; font-weight: 600; padding: 8px 16px;
  border: none; border-radius: 6px; background: #fff; color: var(--rel-verde, #2E5E3E);
  cursor: pointer;
}
.relatorio-toolbar button:disabled { opacity: .5; cursor: default; }
```

E quando a toolbar está visível na tela, o cabeçalho fixo precisa começar abaixo dela. Trocar o `padding-top` do `.relatorio-pagina` em `@media screen` — na verdade a faixa `.rc` fica **por baixo** da toolbar (toolbar `z-index: 50` > `.rc` `z-index: 10`). Melhor: empurrar a faixa. Adicionar em `@media screen`:

```css
@media screen {
  .relatorio-tema body { padding: 24px 0; }
  .relatorio-pagina { box-shadow: 0 2px 24px rgba(0,0,0,.12); border-radius: 4px; }
  :root.relatorio-tema { scroll-padding-top: 48px; }
}
```

e no `RelatorioCabecalho.svelte` `.rc`, em `@media screen` adicionar `top: 44px;` (altura da toolbar). Na impressão a toolbar some (`.no-print`) e a faixa volta pro topo:

No `<style>` do `RelatorioCabecalho.svelte`:

```css
  @media screen { .rc { top: 44px; } }
  @media print { .rc { top: 0; } .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
```

- [ ] **Step 7: Restart + check**

Run: `docker restart datahub_frontend && cd frontend && npm run check`
Esperado: sem erros.

- [ ] **Step 8: Verificação manual (Playwright) — painel inteiro**

`http://localhost:3000/relatorio/painel/lanc_fichas` (empresa `prats` tem dados recentes; logar com admin e trocar pra `prats`, ou usar `alpha`):
- Toolbar verde no topo: "Preparando relatório…" some e o botão "Imprimir / Salvar PDF" habilita em poucos segundos.
- Grid com os indicadores nas posições configuradas: KPIs com suas cores, gráficos renderizados (SVG), tabela com todas as linhas sem paginação, mapa com tiles claros.
- `Ctrl+P` (preview de impressão do Chrome): cabeçalho e rodapé aparecem em todas as páginas; cores de fundo saem (ativar "Gráficos de segundo plano" se preciso).
- Screenshot da tela e do preview de impressão.

- [ ] **Step 9: Verificação manual — indicador único (tabela)**

Pegar o `id` de um `painel_indicador` do tipo `table` ou `table_dynamic` (no DevTools, na resposta de `renderizar`, ou:
`docker exec datahub_postgres psql -U postgres -d datahub_meta -c "SELECT pi.id, pi.titulo, q.tipo FROM painel_indicadores pi JOIN queries q ON q.slug = pi.query_slug WHERE q.tipo IN ('table','table_dynamic') LIMIT 5;"`)

Abrir `http://localhost:3000/relatorio/painel/<slug>?indicador=<id>`:
- Subtítulo do cabeçalho: `RELAÇÃO DE DADOS`.
- Só aquela tabela, largura total, todas as linhas, sem barra de paginação nem botões de export.
- Se tiver > 8 colunas: preview de impressão em paisagem.
- Screenshot.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/lib/components/ChartPanel.svelte frontend/src/lib/components/MapPanel.svelte frontend/src/lib/components/DataTable.svelte frontend/src/lib/components/DynamicTable.svelte frontend/src/lib/relatorio/ frontend/src/routes/relatorio/
git commit -m "$(cat <<'EOF'
feat: corpo do relatorio (grid de indicadores) + prontidao pra impressao

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 6: Frontend — ligar os pontos de entrada e remover o jsPDF

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte` (botão Imprimir, props pras tabelas)
- Modify: `frontend/src/lib/components/DataTable.svelte` (botão PDF → abre rota)
- Modify: `frontend/src/lib/components/DynamicTable.svelte` (botão PDF → abre rota)
- Modify: `frontend/src/lib/exportTable.js` (remove funções de PDF)
- Modify: `frontend/package.json` (remove `jspdf`, `jspdf-autotable`)

**Interfaces:**
- Consumes: rota `/relatorio/painel/<slug>?indicador=<id>&<filtros>` (Task 5); props `painelSlug`/`indicadorId`/`filtrosQuery` já declaradas em `DataTable`/`DynamicTable` (Task 5 Step 3/4).
- Produces:
  - Painel: botão "Imprimir" abre `/relatorio/painel/<slug>?<filtros>`.
  - `DataTable`/`DynamicTable`: botão "🖨 PDF" abre `/relatorio/painel/<slug>?indicador=<id>&<filtros>` em nova aba.
  - `exportTable.js` sem nenhuma referência a jsPDF; exporta só `baixarCSV`, `baixarXLSX`, `baixarCSVAgrupado`, `baixarXLSXAgrupado`.

- [ ] **Step 1: Painel — botão Imprimir + query dos filtros**

Em `frontend/src/routes/painel/[slug]/+page.svelte`:

Adicionar reativo (junto de `resumoFiltrosLista`, ~linha 30):

```js
  $: filtrosQuery = new URLSearchParams(filtrosAtivos).toString();

  function imprimirPainel() {
    window.open(`/relatorio/painel/${slug}?${filtrosQuery}`, '_blank', 'noopener');
  }
```

Trocar o `.painel-header` (~linha 189-194):

```svelte
    <div class="painel-header">
      <div class="painel-header-topo">
        <h2>{painel.nome}</h2>
        <button class="btn-ghost btn-imprimir" on:click={imprimirPainel}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="6 9 6 2 18 2 18 9"/>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
            <rect x="6" y="14" width="12" height="8"/>
          </svg>
          Imprimir
        </button>
      </div>
      {#if painel.descricao}
        <p class="descricao">{painel.descricao}</p>
      {/if}
    </div>
```

No `<style>`, junto de `.painel-header` (~linha 340):

```css
.painel-header-topo { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.btn-imprimir { display: flex; align-items: center; gap: 6px; font-size: 13px; padding: 6px 12px; border-radius: 6px; flex-shrink: 0; }
.btn-imprimir svg { width: 15px; height: 15px; }
```

- [ ] **Step 2: Painel — passar props pras tabelas**

No `<DataTable ...>` (~linha 295-312) adicionar:

```svelte
              <DataTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                painelSlug={slug}
                indicadorId={ind.id}
                filtrosQuery={filtrosQuery}
                impressaoHabilitada={ind.impressao_habilitada}
                ...(resto das props intacto)...
              />
```

No `<DynamicTable ...>` (~linha 314-322):

```svelte
              <DynamicTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                painelSlug={slug}
                indicadorId={ind.id}
                filtrosQuery={filtrosQuery}
                agrupamentos={ind.agrupamentos ?? []}
                agregacoes={ind.agregacoes ?? []}
                subquery={ind.subquery}
                pdfOrientacao={ind.pdf_orientacao}
              />
```

- [ ] **Step 3: `DataTable` — botão PDF abre a rota**

Remover do import (~linha 2): `baixarPDF`. Fica:

```js
  import { baixarCSV, baixarXLSX } from '$lib/exportTable.js';
```

Remover `let gerandoPDF = false;` e a função `async function exportarPDF()` (~linha 79-88). Substituir por:

```js
  function exportarPDF() {
    if (!painelSlug || indicadorId == null) return;
    const p = new URLSearchParams(filtrosQuery);
    p.set('indicador', indicadorId);
    window.open(`/relatorio/painel/${painelSlug}?${p}`, '_blank', 'noopener');
  }
```

Trocar o botão PDF (~linha 163-165):

```svelte
    <button class="btn-export btn-export-pdf btn-sm" on:click={exportarPDF} disabled={dados.length === 0 || !painelSlug}>
      🖨 PDF
    </button>
```

(a prop `pdfOrientacao` fica sem uso agora — pode remover a linha `export let pdfOrientacao` da `DataTable`; a orientação passa a ser decidida pela rota. Remover.)

- [ ] **Step 4: `DynamicTable` — botão PDF abre a rota**

Remover do import (~linha 9): `baixarPDFAgrupado`. Fica:

```js
  import { baixarCSVAgrupado, baixarXLSXAgrupado } from '$lib/exportTable.js';
```

Remover `let gerandoPDF = false;` e `async function exportarPDF()` (~linha 73-81). Substituir:

```js
  function exportarPDF() {
    if (!painelSlug || indicadorId == null) return;
    const p = new URLSearchParams(filtrosQuery);
    p.set('indicador', indicadorId);
    window.open(`/relatorio/painel/${painelSlug}?${p}`, '_blank', 'noopener');
  }
```

Botão PDF (~linha 139-141):

```svelte
    <button class="btn-export btn-export-pdf btn-sm" on:click={exportarPDF} disabled={dados.length === 0 || !painelSlug}>
      🖨 PDF
    </button>
```

Remover a prop `export let pdfOrientacao = 'retrato';` (sem uso).

- [ ] **Step 5: `exportTable.js` — remover jsPDF**

Reescrever `frontend/src/lib/exportTable.js` removendo:
- os imports `import { jsPDF } from 'jspdf';`, `import autoTable from 'jspdf-autotable';`, `import { get } from 'svelte/store';`, `import { empresaAtiva } from '$lib/stores/auth.js';`
- as funções `logoParaDataURL`, `prepararDocumentoPDF`, `desenharCabecalhoPagina`, `numerarPaginasPDF`, `salvarPDF`, `baixarPDF`, `baixarPDFAgrupado`

O arquivo fica com: `escaparCSV`, `baixarCSV`, `baixarXLSX`, `achatarArvore`, `indentar`, `linhasAgrupadasComTipo`, `baixarCSVAgrupado`, `XLSX_FUNDO_*`, `baixarXLSXAgrupado`. Imports que sobram: `import * as XLSX from 'xlsx';` e `import ExcelJS from 'exceljs';`.

- [ ] **Step 6: `package.json` — remover deps**

Em `frontend/package.json`, remover as linhas:

```json
		"jspdf": "^4.2.1",
		"jspdf-autotable": "^5.0.8",
```

Rodar:

```bash
docker exec datahub_frontend npm install
```

- [ ] **Step 7: Conferir que não sobrou referência**

Run: `cd frontend && grep -rn "jspdf\|baixarPDF\|autoTable\|pdfOrientacao" src/`
Esperado: zero resultados.

- [ ] **Step 8: Restart + check**

Run: `docker restart datahub_frontend && cd frontend && npm run check`
Esperado: sem erros.

- [ ] **Step 9: Verificação manual (Playwright)**

1. Painel `lanc_fichas` → botão "Imprimir" no cabeçalho → abre nova aba `/relatorio/painel/lanc_fichas?...` com os filtros ativos na query string e nos chips do cabeçalho.
2. Aplicar um filtro (ex. Fazenda) → "Imprimir" de novo → o relatório reflete o filtro (chip aparece, dados filtrados).
3. Numa tabela do painel → botão "🖨 PDF" → abre nova aba só com aquela tabela, subtítulo `RELAÇÃO DE DADOS`.
4. CSV e Excel das tabelas → continuam baixando arquivo normalmente.
5. Screenshots de 1 e 3.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/routes/painel/ frontend/src/lib/components/DataTable.svelte frontend/src/lib/components/DynamicTable.svelte frontend/src/lib/exportTable.js frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
feat: botao Imprimir no painel + PDF de tabela via rota de relatorio; remove jsPDF

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 7: Verificação end-to-end e handoff de deploy

**Files:** nenhum (só verificação).

- [ ] **Step 1: Suíte backend completa**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Esperado: tudo verde. Anotar o total de testes.

- [ ] **Step 2: `npm run check` limpo**

Run: `cd frontend && npm run check`
Esperado: 0 errors.

- [ ] **Step 3: Walkthrough Playwright completo (com screenshots pro usuário)**

Login `admin@datahub.local` / `admin123`, empresa `prats`:
1. `/configuracoes/empresas/<id prats>` → preencher Endereço e CNPJ reais da empresa → salvar.
2. Painel com KPIs + gráfico + tabela + (se houver) mapa → "Imprimir" → screenshot da aba de relatório + screenshot do preview de impressão do Chrome (`Ctrl+P`).
3. Tabela → "🖨 PDF" → screenshot.
4. Enviar os screenshots pro usuário via SendUserFile.

- [ ] **Step 4: Checklist de deploy (produção) — passar pro usuário**

O usuário roda no terminal do serviço `postgres` do EasyPanel (`psql -U postgres -d datahub_meta` — ver memória `prod-postgres-role`):

```sql
ALTER TABLE empresas ADD COLUMN endereco TEXT;
ALTER TABLE empresas ADD COLUMN cnpj VARCHAR(20);
```

Depois: deploy de `backend` e `frontend` no EasyPanel. Se não refletir — reincidência conhecida — "Forçar reconstrução"; se ainda não, **Stop → aguardar parar → Start** (não confiar no "Restart"). Diagnóstico rápido: `curl -sI https://bi.psosistemas.com.br/ | grep -i last-modified` vs. horário do commit.

Pós-deploy: preencher Endereço/CNPJ das empresas reais (`prats`, `vitoria-agronegocios`) pela tela de config; abrir um painel em produção → "Imprimir" → conferir cabeçalho.

- [ ] **Step 5: Nota de memória**

Após o deploy confirmado pelo usuário, atualizar a memória do projeto:
- `project-datahub-overview.md`: nova seção da feature de impressão/relatório + mover o delta `empresas.endereco/cnpj` de "pendente" pra "aplicado em produção em <data>".
- Atualizar `MEMORY.md` (a linha do overview).

---

## Self-Review

**1. Spec coverage**

| Spec | Task |
|---|---|
| Schema `empresas.endereco` + `cnpj` | Task 1 (Step 1, 11) |
| Backend models/SELECT/INSERT/UPDATE + `/me` | Task 1 (Steps 5-8) |
| Teste backend | Task 1 (Step 3) |
| `conftest.hard_delete_empresa` | Task 1 (Step 2) |
| README "Deltas pendentes" + `init-meta-prod.sql` | Task 1 (Step 11) |
| `tema-relatorio.css` (paleta, `@page`, `@media print`) | Task 4 (Step 1), Task 5 (Step 6) |
| `RelatorioCabecalho` (faixa, logo, subtítulo, empresa, chips, arcos SVG) | Task 4 (Step 3) |
| `RelatorioRodape` (fixed, repete) | Task 4 (Step 2) |
| `$lib/resumoFiltros.js` refactor | Task 3 |
| Rota `/relatorio/painel/[slug]` — modo painel (grid preservado) | Task 5 (Step 5) |
| Rota — modo `?indicador=<id>` (tabela sem paginação, thead repetido, landscape auto) | Task 5 (Steps 3-5) |
| Carve-out no `+layout.svelte` mantendo auth | Task 4 (Step 4) |
| `empresaAtiva` ganha `endereco`/`cnpj` | Task 4 (Step 5) |
| Força paleta clara no `<html>` (classe `relatorio-tema`) + desfaz no destroy | Task 4 (Step 6), Task 5 (Step 5) |
| `ChartPanel` emite `pronto` | Task 5 (Step 1) |
| `MapPanel` emite `pronto` + `temaForcado` | Task 5 (Step 2) |
| `DataTable`/`DynamicTable` `modoRelatorio` | Task 5 (Steps 3-4) |
| Toolbar "Imprimir / Salvar PDF" habilitada quando pronto; sem auto-print | Task 5 (Step 5) |
| Botão "Imprimir" no cabeçalho do painel | Task 6 (Step 1) |
| Botão PDF de `table`/`table_dynamic` abre a rota; CSV/Excel iguais | Task 6 (Steps 3-4) |
| Remover `baixarPDF`/`baixarPDFAgrupado` + deps jsPDF | Task 6 (Steps 5-6) |
| KPI/chart mantêm cores (sem override) | respeitado — nenhuma task muda cor de KPI/chart |
| Textos fixos exatos | Task 4 (Steps 2-3), Task 5 (Step 5) — `RELATÓRIO DE INDICADORES`/`RELAÇÃO DE DADOS`, `DataHub · GPA Analytics` |
| Riscos (tiles do mapa, cabeçalho fixo sobrepondo, cores de fundo) | Task 5 (Steps 2, 6, 8) |
| Deploy (delta em prod, Stop→Start) | Task 7 (Step 4) |
| Nota de memória | Task 7 (Step 5) |

Sem lacunas.

**2. Placeholder scan**

Nenhum "TBD"/"TODO"/"handle edge cases". O único "placeholder" é intencional e explícito: o corpo da rota na Task 4 (lista de títulos) que a Task 5 Step 5 substitui pelo grid real — as duas tasks mostram o código completo.

**3. Type consistency**

- `resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel)` — mesma assinatura em Task 3 (definição), Task 4 Step 6 e Task 5 Step 5 (uso). Retorno `[{nome, valor}]` consumido por `RelatorioCabecalho` prop `filtros` (Task 4 Step 3). ✓
- `marcarPronto(id)` / evento `on:pronto` — `ChartPanel`/`MapPanel` fazem `dispatch('pronto')` sem payload (Task 5 Steps 1-2); a rota faz `on:pronto={() => marcarPronto(ind.id)}` (Task 5 Step 5). ✓
- `modoRelatorio` (boolean) — declarado em `DataTable`/`DynamicTable` (Task 5 Steps 3-4), passado pela rota (Task 5 Step 5). ✓
- `painelSlug` / `indicadorId` / `filtrosQuery` — declarados em Task 5 Steps 3-4, preenchidos pelo painel em Task 6 Step 2, consumidos por `exportarPDF()` em Task 6 Steps 3-4. ✓
- `temaForcado` — `MapPanel` (Task 5 Step 2), passado `temaForcado="claro"` pela rota (Task 5 Step 5). ✓
- `company_endereco` / `company_cnpj` — produzidos por `/me` (Task 1 Step 5), lidos pela rota (`me.company_endereco`) e pelo layout (Task 4 Steps 5-6). ✓
- Classe `relatorio-tema` no `<html>` — adicionada/removida na rota (Task 4 Step 6 / Task 5 Step 5), alvo do seletor `:root.relatorio-tema` no CSS (Task 4 Step 1). ✓
- `.no-print` — usada na toolbar (Task 5 Step 5) e escondida no `@media print` (Task 4 Step 1). ✓

Consistente.
