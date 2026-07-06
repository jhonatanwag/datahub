# DataTable Pagination and CSV Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick a page size (10/50/100/500) for `table`-type painel widgets and download the full query result as a CSV, without changing the backend.

**Architecture:** `DataTable.svelte` gains internal pagination state (`paginaAtual`, `tamanhoPagina`) that slices the already-fully-fetched `dados` array client-side, replacing the unused `total`/`page` prop contract nobody ever wired up. A `baixarCSV()` function builds a semicolon-delimited, UTF-8-BOM CSV from the full `dados` array (not just the current page) and triggers a browser download via a Blob + temporary `<a>` element — no new dependency.

**Tech Stack:** SvelteKit (Svelte 5, plain JS, no TypeScript). No new npm packages.

## Global Constraints

- No TypeScript anywhere in the frontend — plain JS only.
- No new npm dependency (CSV export uses only native Blob/URL/`<a download>` APIs — no SheetJS/xlsx).
- Default page size is 50; selectable values are exactly 10, 50, 100, 500.
- CSV export always includes the full `dados` array, regardless of the current page being viewed.
- CSV uses `;` as the field delimiter and a UTF-8 BOM prefix (Excel PT-BR convention).
- Design reference: `docs/superpowers/specs/2026-07-06-datatable-pagination-export-design.md`.

---

### Task 1: Pagination + CSV export in DataTable, wired into the painel page

**Files:**
- Modify: `frontend/src/lib/components/DataTable.svelte` (full rewrite)
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte:197` (pass new `titulo` prop)

**Interfaces:**
- Consumes: `colunasEfetivas` derivation already present in `DataTable.svelte` (from the prior `fix/datatable-dynamic-columns` fix — falls back to `Object.keys(dados[0])` when `colunas` isn't passed).
- Produces: `DataTable` props become `colunas` (unchanged), `dados` (unchanged), `titulo` (new, optional, default `'dados'`). The old `total`/`page` props and the `dispatch('page', ...)` event are removed — nothing in the codebase consumes them.

- [ ] **Step 1: Replace `DataTable.svelte` with the paginated + exportable version**

Replace the full contents of `frontend/src/lib/components/DataTable.svelte` with:

```svelte
<script>
  export let colunas = [];
  export let dados   = [];
  export let titulo  = 'dados';

  const TAMANHOS_PAGINA = [10, 50, 100, 500];
  let paginaAtual   = 1;
  let tamanhoPagina = 50;

  // Queries dinâmicas não têm schema fixo — se o chamador não informar as
  // colunas, deriva a partir das chaves da primeira linha retornada.
  $: colunasEfetivas = colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : []);

  $: totalPaginas = Math.max(1, Math.ceil(dados.length / tamanhoPagina));
  $: dadosPaginados = dados.slice(
    (paginaAtual - 1) * tamanhoPagina,
    paginaAtual * tamanhoPagina
  );

  // Reseta para a página 1 sempre que os dados mudam (novo filtro aplicado)
  // ou o tamanho de página muda, pra nunca ficar numa página vazia/inválida.
  $: dados, tamanhoPagina, (paginaAtual = 1);

  const fmtValor = (v) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);

  const STATUS_COLOR = {
    concluido: 'var(--accent-green)',
    pendente:  'var(--accent-orange)',
    cancelado: 'var(--accent)',
  };

  function escaparCSV(valor) {
    const texto = valor === null || valor === undefined ? '' : String(valor);
    if (/[;"\n]/.test(texto)) {
      return `"${texto.replace(/"/g, '""')}"`;
    }
    return texto;
  }

  function baixarCSV() {
    const cabecalho = colunasEfetivas.map(c => escaparCSV(c.label ?? c.key)).join(';');
    const linhas = dados.map(row =>
      colunasEfetivas.map(c => escaparCSV(row[c.key])).join(';')
    );
    const conteudo = '﻿' + [cabecalho, ...linhas].join('\r\n');
    const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.csv`;

    const a = document.createElement('a');
    a.href = url;
    a.download = nomeArquivo;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunasEfetivas as col}
          <th>{col.label ?? col.key}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each dadosPaginados as row}
        <tr>
          {#each colunasEfetivas as col}
            <td>
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="pagination">
    <button class="btn-ghost btn-sm" on:click={baixarCSV} disabled={dados.length === 0}>
      ⬇ Baixar CSV
    </button>
    <span>{dados.length} registros</span>
    <label class="tamanho-pagina">
      Itens por página:
      <select bind:value={tamanhoPagina}>
        {#each TAMANHOS_PAGINA as tam}
          <option value={tam}>{tam}</option>
        {/each}
      </select>
    </label>
    <div class="btns">
      <button class="btn-ghost" on:click={() => paginaAtual -= 1} disabled={paginaAtual <= 1}>← Anterior</button>
      <span>Pág {paginaAtual} / {totalPaginas}</span>
      <button class="btn-ghost" on:click={() => paginaAtual += 1} disabled={paginaAtual >= totalPaginas}>Próxima →</button>
    </div>
  </div>
</div>

<style>
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
tr:hover td { background: var(--surface2); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0 0;
  color: var(--muted);
  font-size: 13px;
  gap: 12px;
  flex-wrap: wrap;
}
.btns { display: flex; gap: 8px; align-items: center; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.tamanho-pagina { display: flex; align-items: center; gap: 6px; }
.tamanho-pagina select { width: auto; padding: 4px 8px; }
</style>
```

- [ ] **Step 2: Pass the `titulo` prop from the painel page**

Edit `frontend/src/routes/painel/[slug]/+page.svelte`, change line 197 from:

```svelte
            {:else if ind.query_tipo === 'table'}
              <DataTable dados={ind.dados} />
```

to:

```svelte
            {:else if ind.query_tipo === 'table'}
              <DataTable dados={ind.dados} titulo={ind.titulo || ind.query_slug} />
```

- [ ] **Step 3: Restart the frontend container and confirm a clean build**

Run:

```bash
docker restart datahub_frontend
docker logs datahub_frontend --tail 30
```

Expected: no Svelte/Vite compilation errors (pre-existing unrelated warnings like the `FiltroVariavel.svelte` a11y warning and `/api/empresas/*/logo` 404s are fine).

- [ ] **Step 4: Verify end-to-end with a real browser (Playwright)**

There is no automated frontend test suite in this project (consistent with the rest of the codebase). Verify by driving a real headless Chromium against the running app — Playwright is available via `npx playwright` (already used and installed in a prior session at `C:\Users\JHONAT~1\AppData\Local\Temp\claude\C--Users-jhonatanw-git-datahub\fa9b5788-b575-43c9-8b61-9c3edb18ce1c\scratchpad`; if that directory is gone, `cd` anywhere, `npm init -y && npm install playwright@1.61.1 && npx playwright install chromium`).

Write and run a script equivalent to:

```js
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', 'admin@datahub.local');
  await page.fill('input[type="password"]', 'admin123');
  await page.click('button:has-text("Entrar")');
  await page.waitForURL('**/selecionar-empresa', { timeout: 10000 }).catch(() => {});
  await page.click('text=Prats');
  await page.waitForURL('**/', { timeout: 10000 }).catch(() => {});

  await page.goto('http://localhost:3000/painel/lanc_fichas', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('.painel-grid', { timeout: 15000 });
  await page.waitForTimeout(1000);

  // Default page size is 50
  const rowsDefault = await page.locator('.grid-item table tbody tr').count();
  console.log('rows with default page size:', rowsDefault);

  // Switch to 500 and confirm the row count changes accordingly
  await page.selectOption('.grid-item select', '500');
  await page.waitForTimeout(300);
  const rows500 = await page.locator('.grid-item table tbody tr').count();
  console.log('rows with page size 500:', rows500);

  // Pagination controls
  const paginaTexto = await page.locator('.grid-item .btns span').textContent();
  console.log('pagina label:', paginaTexto);

  // Download
  const [ download ] = await Promise.all([
    page.waitForEvent('download'),
    page.click('.grid-item button:has-text("Baixar CSV")'),
  ]);
  const path = await download.path();
  const fs = require('fs');
  const content = fs.readFileSync(path, 'latin1'); // BOM-safe enough for a line count check
  const lineCount = content.split(/\r\n|\n/).filter(Boolean).length;
  console.log('suggested filename:', download.suggestedFilename());
  console.log('csv line count (header + rows):', lineCount);

  await browser.close();
})().catch(e => { console.error('SCRIPT ERROR:', e); process.exit(1); });
```

Expected:
- `rows with default page size` → `50`
- `rows with page size 500` → `500`
- `pagina label` → matches `Pág 1 / <ceil(47995/500)>` when on page size 500 (adjust to whatever page size was active when read — read it right after switching to 500)
- `suggested filename` → ends in `.csv`, derived from the indicator's título (e.g. `Lancamentos_Negativos.csv`)
- `csv line count` → `47996` (1 header row + 47995 data rows) — i.e. the full dataset, not just the current page

- [ ] **Step 5: Verify the empty-data case doesn't break**

Using the same Playwright session pattern, log in and select empresa "Vitória Agronegócios" instead of "Prats" (its `lancamento_ficha` data ends before the default "ano atual" filter window, so the painel legitimately returns zero rows — confirmed in the prior debugging session). Navigate to `/painel/lanc_fichas` and confirm:
- The "Baixar CSV" button is present but `disabled` (check `await page.locator('.grid-item button:has-text("Baixar CSV")').isDisabled()` → `true`)
- No console errors beyond the pre-existing `/logo` 404s
- Pagination shows "Pág 1 / 1" without throwing (division-by-zero guarded by `Math.max(1, ...)` in `totalPaginas`)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/DataTable.svelte frontend/src/routes/painel/[slug]/+page.svelte
git commit -m "feat: add page-size selector and CSV export to DataTable"
```
