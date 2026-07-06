# XLSX Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Baixar Excel" button next to the existing "Baixar CSV" button in `DataTable`, exporting the full query result as a real `.xlsx` file with preserved value types (numbers stay numbers).

**Architecture:** Add the `xlsx` (SheetJS Community Edition) npm package. A new `baixarXLSX()` function builds an array-of-arrays from `colunasEfetivas` (header) + the full `dados` array (rows), converts it to a worksheet via `XLSX.utils.aoa_to_sheet`, and triggers the download via `XLSX.writeFile` — the library handles the download mechanism itself, unlike the manual Blob/`<a>` approach used for CSV.

**Tech Stack:** SvelteKit (Svelte 5, plain JS, no TypeScript). New dependency: `xlsx@0.18.5`.

## Global Constraints

- No TypeScript anywhere in the frontend — plain JS only.
- CSV export must keep working exactly as before — this is an addition, not a replacement.
- XLSX export always includes the full `dados` array, not just the current page (same rule as CSV).
- No cell styling (bold headers, colors, column widths) — out of scope per the spec.
- Design reference: `docs/superpowers/specs/2026-07-06-xlsx-export-design.md`.

---

### Task 1: Add XLSX export button and function to DataTable

**Files:**
- Modify: `frontend/package.json` (add `xlsx` dependency)
- Modify: `frontend/src/lib/components/DataTable.svelte`

**Interfaces:**
- Consumes: `colunasEfetivas` (existing derivation, `frontend/src/lib/components/DataTable.svelte:12-14`), `dados` (existing prop), `titulo` (existing prop).
- Produces: `baixarXLSX()` function, in-component only (no external consumers).

- [ ] **Step 1: Add the `xlsx` dependency**

Edit `frontend/package.json`, add to the `"dependencies"` block (currently `echarts` and `leaflet`):

```json
	"dependencies": {
		"echarts": "^6.1.0",
		"leaflet": "^1.9.4",
		"xlsx": "^0.18.5"
	}
```

- [ ] **Step 2: Install the dependency in the frontend container**

Run:

```bash
docker exec datahub_frontend npm install
```

Expected: `xlsx` appears in `frontend/node_modules/xlsx` and in `frontend/package-lock.json` (or `npm install` output shows it added, no errors).

- [ ] **Step 3: Import xlsx and add `baixarXLSX()`**

Edit `frontend/src/lib/components/DataTable.svelte`. Add the import at the very top of the `<script>` block (before `export let colunas = [];`):

```js
  import * as XLSX from 'xlsx';

```

Add the new function right after the existing `baixarCSV()` function (after its closing `}` on line 66):

```js

  function baixarXLSX() {
    const cabecalho = colunasEfetivas.map(c => c.label ?? c.key);
    const linhas = dados.map(row =>
      colunasEfetivas.map(c => row[c.key] ?? '')
    );
    const ws = XLSX.utils.aoa_to_sheet([cabecalho, ...linhas]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Dados');
    const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.xlsx`;
    XLSX.writeFile(wb, nomeArquivo);
  }
```

- [ ] **Step 4: Add the second button to the footer**

Edit `frontend/src/lib/components/DataTable.svelte`, replace:

```svelte
    <button class="btn-ghost btn-sm" on:click={baixarCSV} disabled={dados.length === 0}>
      ⬇ Baixar CSV
    </button>
```

with:

```svelte
    <button class="btn-ghost btn-sm" on:click={baixarCSV} disabled={dados.length === 0}>
      ⬇ CSV
    </button>
    <button class="btn-ghost btn-sm" on:click={baixarXLSX} disabled={dados.length === 0}>
      ⬇ Excel
    </button>
```

- [ ] **Step 5: Restart the frontend and confirm a clean build**

Run:

```bash
docker restart datahub_frontend
docker logs datahub_frontend --tail 30
```

Expected: no Vite/Svelte compilation errors related to the `xlsx` import (pre-existing unrelated warnings — the `FiltroVariavel.svelte` a11y warning and `/api/empresas/*/logo` 404s — are fine).

- [ ] **Step 6: Verify end-to-end with a real browser (Playwright)**

There is no automated frontend test suite in this project. Verify by driving a real headless Chromium against the running app (Playwright is available via `npx playwright`; if not already installed in the environment, `npm install playwright@1.61.1 && npx playwright install chromium` in a scratch directory).

Write and run a script equivalent to:

```js
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', 'admin@datahub.local');
  await page.fill('input[type="password"]', 'admin123');
  await page.click('button:has-text("Entrar")');
  await page.waitForURL('**/selecionar-empresa', { timeout: 10000 }).catch(() => {});
  await page.click('text=Prats');
  await page.waitForURL('**/', { timeout: 10000 }).catch(() => {});

  await page.goto('http://localhost:3000/painel/lanc_fichas', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('.painel-grid', { timeout: 15000 });
  await page.waitForTimeout(800);

  // Both buttons present and enabled (there is data)
  const csvDisabled   = await page.locator('.grid-item button:has-text("CSV")').isDisabled();
  const excelDisabled = await page.locator('.grid-item button:has-text("Excel")').isDisabled();

  const [ download ] = await Promise.all([
    page.waitForEvent('download'),
    page.click('.grid-item button:has-text("Excel")'),
  ]);
  const path = await download.path();
  console.log(JSON.stringify({
    csvDisabled, excelDisabled,
    suggestedFilename: download.suggestedFilename(),
  }));

  const fs = require('fs');
  fs.copyFileSync(path, './downloaded.xlsx');

  await browser.close();
})().catch(e => { console.error('SCRIPT ERROR:', e); process.exit(1); });
```

Expected: `csvDisabled: false`, `excelDisabled: false`, `suggestedFilename` ends in `.xlsx` and matches the indicator's título (e.g. `Lancamentos_Negativos.xlsx`).

Then, in the same or a follow-up Node script, read back `./downloaded.xlsx` with the same `xlsx` library to confirm its contents (install it in the scratch dir: `npm install xlsx@0.18.5`):

```js
const XLSX = require('xlsx');
const wb = XLSX.readFile('./downloaded.xlsx');
const ws = wb.Sheets[wb.SheetNames[0]];
const rows = XLSX.utils.sheet_to_json(ws, { header: 1 });
console.log('total rows (header + data):', rows.length);
console.log('header:', rows[0]);
console.log('first data row:', rows[1]);
const qtdColIndex = rows[0].indexOf('qtd');
console.log('qtd value type in row 2:', typeof rows[1][qtdColIndex]);
```

Expected: `total rows` → `47996` (1 header + 47995 data rows, matching the CSV count from the prior fix); `header` → the 9 column names in order; `qtd value type` → `'number'` (not `'string'`) — confirms type preservation.

- [ ] **Step 7: Verify the previously-broken multi-line records are intact**

In the same read-back script, search for a row containing the known embedded-newline text and confirm it's a single row, not split:

```js
const idx = rows.findIndex(r => String(r).includes('AS MANGUEIRAS DO SISTEMA DE AR'));
console.log('found at row index:', idx, '- full row:', rows[idx]);
```

Expected: exactly one row found, with all 9 columns present and correctly positioned (not split into a truncated row + orphaned fragment, unlike the pre-fix CSV bug).

- [ ] **Step 8: Verify the empty-data case**

Using the same Playwright pattern, log in and select empresa "Vitória Agronegócios" (whose `lancamento_ficha` data falls outside the default date filter, per the prior debugging session — this painel legitimately returns zero rows for that company). Navigate to `/painel/lanc_fichas` and confirm both `button:has-text("CSV")` and `button:has-text("Excel")` report `isDisabled() === true`.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/components/DataTable.svelte
git commit -m "feat: add XLSX export option to DataTable"
```
