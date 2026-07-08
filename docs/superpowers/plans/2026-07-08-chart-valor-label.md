# Nome de Exibição do Valor no Gráfico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir sobrescrever o nome de exibição da série `valor` na legenda/tooltip de `chart_bar`/`chart_bar_horizontal`/`chart_line`, sem alterar a validação de contrato que continua exigindo a coluna `valor`.

**Architecture:** Nova coluna opcional `queries.chart_valor_label` (nullable), exposta no CRUD e propagada por `renderizar_painel`, consumida por `ChartPanel.svelte` só como um mapeamento de exibição — a coluna `valor` continua existindo tecnicamente, só o texto mostrado muda.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, ECharts, PostgreSQL

## Global Constraints

- Campo só aparece na UI pra `chart_bar`, `chart_bar_horizontal`, `chart_line` — não pra `chart_doughnut` (fatias já são nomeadas por `label`, não por `valor`)
- Nullable, sem validação — texto livre opcional
- Vazio/null preserva o comportamento atual (mostra "valor")
- Sem sistema de migrations — `ALTER TABLE` manual + refletir em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`

---

## Task 1: Nome de exibição do valor — ponta a ponta

**Files:**
- Modify: `scripts/init-db.sql`, `scripts/init-meta-prod.sql`
- Modify: `backend/routes/queries.py`
- Modify: `backend/routes/paineis.py`
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte`
- Modify: `frontend/src/lib/components/ChartPanel.svelte`
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

- [ ] **Step 1: Schema**

```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE queries ADD COLUMN chart_valor_label VARCHAR(50);"
```

Adicionar `chart_valor_label VARCHAR(50),` no bloco `CREATE TABLE queries` de `scripts/init-db.sql` e `scripts/init-meta-prod.sql` (logo após `chart_mostrar_valor`), e no README.md, seção "Deltas de schema pendentes":

```sql
-- 2026-07-08 — nome de exibição customizado pra série "valor" no gráfico
ALTER TABLE queries ADD COLUMN chart_valor_label VARCHAR(50);
```

- [ ] **Step 2: Backend — `queries.py`**

`QueryInput`/`QueryUpdate`: adicionar `chart_valor_label: Optional[str] = None`.

`criar_query`: incluir no INSERT (16 colunas agora, `$16`).

`atualizar_query`: incluir `'chart_valor_label'` em `ALLOWED_COLS`.

- [ ] **Step 3: Backend — `paineis.py`**

Incluir `q.chart_valor_label` no SELECT de `renderizar_painel` (junto dos outros `chart_*`).

- [ ] **Step 4: Frontend — `nova/+page.svelte` e `[id]/+page.svelte`**

Adicionar `chart_valor_label: ''` ao form (nova) / carregar `q.chart_valor_label || ''` (edição). No bloco "Configurações do Gráfico" já existente, adicionar dentro de um `{#if ['chart_bar','chart_bar_horizontal','chart_line'].includes(form.tipo)}`:

```svelte
<label class="lbl">
  Nome de exibição do valor principal (opcional)
  <input type="text" bind:value={form.chart_valor_label} placeholder="ex: Perdas" style="width:180px" />
</label>
```

No `[id]/+page.svelte`, incluir `chart_valor_label: form.chart_valor_label || null,` no payload de `salvar()`.

- [ ] **Step 5: `ChartPanel.svelte`**

Nova prop `valorLabel = null`. Função helper:

```js
function nomeSerie(col) {
  return col === 'valor' && valorLabel ? valorLabel : col;
}
```

Usar `nomeSerie(col)` em vez de `col` cru em `series[].name` e em `legend.data`.

- [ ] **Step 6: `painel/[slug]/+page.svelte`**

Passar `valorLabel={ind.chart_valor_label}` pro `ChartPanel`.

- [ ] **Step 7: Verificação manual completa**

1. Criar query `chart_bar` multi-série sem preencher "Nome de exibição" — legenda mostra "valor" (sem regressão).
2. Preencher "Perdas" — legenda/tooltip mostram "Perdas".
3. Confirmar `chart_doughnut` não mostra o campo novo.
4. Salvar, recarregar painel — reflete na hora (cache já corrigido).

- [ ] **Step 8: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md backend/routes/queries.py backend/routes/paineis.py frontend/src/routes/configuracoes/queries/nova/+page.svelte "frontend/src/routes/configuracoes/queries/[id]/+page.svelte" frontend/src/lib/components/ChartPanel.svelte frontend/src/routes/painel/[slug]/+page.svelte
git commit -m "feat: allow overriding the display name of the chart 'valor' series"
```
