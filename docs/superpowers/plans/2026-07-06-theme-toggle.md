# Theme Toggle (claro/escuro) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each user switch between a light and a dark theme from a topbar button, with the choice persisted on their account (works across browsers/devices) and applied automatically on future logins.

**Architecture:** A `tema` column (`'claro'|'escuro'`) is added to `usuarios`. `middleware/auth.py` already re-queries the DB on every authenticated request, so adding `u.tema` there makes it available on `/api/auth/me` for free. A new `PUT /api/auth/tema` endpoint lets the logged-in user update their own value. The frontend sets a `data-theme` attribute on `<html>` from `$usuario.tema`; `app.css` already uses CSS variables everywhere, so a single `:root[data-theme="claro"]` override block re-themes the whole app. `ChartPanel` (ECharts) and `MapPanel` (Leaflet) hardcode dark-theme colors today and need to read the live theme to stay legible in light mode.

**Tech Stack:** FastAPI + asyncpg (backend, Python 3.12), SvelteKit/Svelte 5 plain JS (frontend, no TypeScript), PostgreSQL, pytest (new, backend only — frontend changes are visual/CSS and verified manually).

## Global Constraints

- No TypeScript anywhere in the frontend — plain JS `.svelte`/`.js` files only.
- Follow existing naming: Portuguese field/variable names (`tema`, `claro`, `escuro`), matching `nome`, `ativo`, `senha`, etc.
- Backend: no ORM — raw SQL via `asyncpg`/`query_meta`, matching every existing route.
- Default value for `tema` is `'escuro'` — must not change the experience of existing users who never touch the toggle.
- Only two theme values: `'claro'` and `'escuro'`. No "follow system" option.
- Design reference: `docs/superpowers/specs/2026-07-06-theme-toggle-design.md`.

---

### Task 1: Backend — `tema` column, `/me` exposure, `PUT /api/auth/tema`, pytest suite

**Files:**
- Modify: `scripts/init-db.sql` (`CREATE TABLE usuarios` block, ~line 35-43)
- Modify: `backend/middleware/auth.py:35-42` (SELECT in `get_current_user`)
- Modify: `backend/routes/auth.py` (add `Literal` import, `TemaInput` model, new endpoint)
- Modify: `backend/requirements.txt` (add `pytest`)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth_tema.py`

**Interfaces:**
- Produces: `PUT /api/auth/tema` — body `{"tema": "claro"|"escuro"}`, auth required (any role), returns `{"tema": "claro"|"escuro"}`, 422 on invalid value, 403 with no `Authorization` header.
- Produces: `user["tema"]` now present in the dict returned by `get_current_user` (and therefore in `GET /api/auth/me`) everywhere in the backend.

- [ ] **Step 1: Add the `tema` column to the schema file**

Edit `scripts/init-db.sql`, in the `CREATE TABLE usuarios` block:

```sql
CREATE TABLE usuarios (
    id           SERIAL PRIMARY KEY,
    nome         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    senha_hash   VARCHAR(255) NOT NULL,
    role         VARCHAR(20) DEFAULT 'viewer',
    ativo        BOOLEAN DEFAULT true,
    tema         VARCHAR(10) NOT NULL DEFAULT 'escuro',
    criado_em    TIMESTAMP DEFAULT NOW()
);
```

This only affects fresh installs (the file runs once when the Postgres volume is created). Step 2 applies the same change to the already-running dev database.

- [ ] **Step 2: Apply the column to the running dev database**

Run:

```bash
docker exec datahub_postgres env PGPASSWORD=postgres123 psql -U postgres -d datahub_meta -c "ALTER TABLE usuarios ADD COLUMN tema VARCHAR(10) NOT NULL DEFAULT 'escuro';"
```

Expected: `ALTER TABLE`

- [ ] **Step 3: Verify the column exists**

Run:

```bash
docker exec datahub_postgres env PGPASSWORD=postgres123 psql -U postgres -d datahub_meta -c "SELECT id, email, tema FROM usuarios;"
```

Expected: a table with a `tema` column, existing rows showing `escuro`.

- [ ] **Step 4: Add pytest to backend dependencies**

Edit `backend/requirements.txt`, append:

```
pytest==8.2.2
```

- [ ] **Step 5: Rebuild and restart the backend container with the new dependency**

Run:

```bash
docker compose -f docker-compose.dev.yml up -d --build backend
```

- [ ] **Step 6: Verify pytest is installed**

Run:

```bash
docker exec datahub_backend python -m pytest --version
```

Expected: `pytest 8.2.2`

- [ ] **Step 7: Write the test fixtures**

Create `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app

ADMIN_EMAIL = "admin@datahub.local"
ADMIN_SENHA = "admin123"
EMPRESA_SLUG = "alpha"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_token(client):
    login_res = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "senha": ADMIN_SENHA},
    )
    assert login_res.status_code == 200
    body = login_res.json()
    empresa = next(e for e in body["empresas"] if e["slug"] == EMPRESA_SLUG)

    sel_res = client.post(
        "/api/auth/selecionar-empresa",
        json={"session_token": body["session_token"], "empresa_id": empresa["id"]},
    )
    assert sel_res.status_code == 200
    token = sel_res.json()["token"]

    yield token

    # Restaura o padrão para não deixar o usuário admin (compartilhado entre
    # execuções de teste) marcado como 'claro' depois da suíte rodar.
    client.put(
        "/api/auth/tema",
        json={"tema": "escuro"},
        headers={"Authorization": f"Bearer {token}"},
    )
```

- [ ] **Step 8: Write the failing tests**

Create `backend/tests/test_auth_tema.py`:

```python
def test_atualizar_tema_valor_valido(client, auth_token):
    res = client.put(
        "/api/auth/tema",
        json={"tema": "claro"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    assert res.json() == {"tema": "claro"}

    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["tema"] == "claro"


def test_atualizar_tema_valor_invalido(client, auth_token):
    res = client.put(
        "/api/auth/tema",
        json={"tema": "azul"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 422


def test_atualizar_tema_sem_autenticacao(client):
    res = client.put("/api/auth/tema", json={"tema": "claro"})
    assert res.status_code == 403
```

- [ ] **Step 9: Run the tests and confirm they fail for the right reason**

Run:

```bash
docker exec datahub_backend python -m pytest tests/test_auth_tema.py -v
```

Expected: `test_atualizar_tema_valor_valido` and `test_atualizar_tema_valor_invalido` FAIL with `assert 404 == 200` / `assert 404 == 422` (route doesn't exist yet). `test_atualizar_tema_sem_autenticacao` FAILs with `assert 404 == 403`.

- [ ] **Step 10: Expose `tema` in `get_current_user`**

In `backend/middleware/auth.py`, replace the SELECT (lines 35-42):

```python
    rows = await query_meta("""
        SELECT u.id, u.nome, u.role, u.tema,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, user_id, empresa_id)
```

- [ ] **Step 11: Add the `PUT /api/auth/tema` endpoint**

In `backend/routes/auth.py`, add the import at the top (alongside the existing ones):

```python
from typing import Literal
```

Add the request model, next to `SelecionarEmpresaInput`:

```python
class TemaInput(BaseModel):
    tema: Literal['claro', 'escuro']
```

Add the endpoint, after the `/me` endpoint (after line 160):

```python
@router.put("/tema")
async def atualizar_tema(body: TemaInput, user=Depends(get_current_user)):
    try:
        await query_meta("UPDATE usuarios SET tema = $1 WHERE id = $2", body.tema, user["id"])
        return {"tema": body.tema}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar tema: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")
```

- [ ] **Step 12: Restart the backend and run the tests again**

Run:

```bash
docker restart datahub_backend
docker exec datahub_backend python -m pytest tests/test_auth_tema.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 13: Commit**

```bash
git add scripts/init-db.sql backend/middleware/auth.py backend/routes/auth.py backend/requirements.txt backend/tests/conftest.py backend/tests/test_auth_tema.py
git commit -m "feat: add user theme preference (tema) with PUT /api/auth/tema"
```

---

### Task 2: Frontend — theme application mechanism + light palette

**Files:**
- Modify: `frontend/src/app.css` (add light palette override block)
- Modify: `frontend/src/routes/+layout.svelte` (reactive `data-theme` application)

**Interfaces:**
- Consumes: `$usuario.tema` (`'claro'|'escuro'`) from `frontend/src/lib/stores/auth.js` — populated automatically once Task 1 ships, since `usuario.set(me)` (called in `+layout.svelte:83` and `selecionar-empresa/+page.svelte:37`) now includes `tema` in `me`.
- Produces: `document.documentElement` carries `data-theme="claro"` or `data-theme="escuro"` whenever a user is logged in; every component styled with the existing CSS variables (`--bg`, `--surface`, `--surface2`, `--border`, `--text`, `--muted`, `--accent*`) re-themes automatically.

- [ ] **Step 1: Add the light palette override to `app.css`**

Edit `frontend/src/app.css`, add this block right after the existing `:root { ... }` block (after line 20):

```css
:root[data-theme="claro"] {
  --bg:          #ffffff;
  --surface:     #f6f8fa;
  --surface2:    #eaeef2;
  --border:      #d0d7de;
  --text:        #1f2328;
  --muted:       #656d76;
  --accent:      #bc4c00;
  --accent-blue: #0969da;
  --accent-green:#1a7f37;
  --danger:      #cf222e;
  --accent-purple:#8250df;
  --accent-orange:#9a6700;
}
```

- [ ] **Step 2: Apply the theme attribute reactively in the root layout**

Edit `frontend/src/routes/+layout.svelte`, add this reactive statement right after the existing ones (after line 122, `$: tooltipAtivo = collapsed;`):

```js
$: if (typeof document !== 'undefined' && $usuario?.tema) {
    document.documentElement.setAttribute('data-theme', $usuario.tema);
}
```

- [ ] **Step 3: Restart the frontend and verify manually**

Run:

```bash
docker restart datahub_frontend
```

Open `http://localhost:3000`, log in as `admin@datahub.local` / `admin123` (empresa `alpha`). The app should look exactly as before (dark theme, since `tema` defaults to `'escuro'`).

Open the browser devtools console and run:

```js
document.documentElement.setAttribute('data-theme', 'claro')
```

Expected: sidebar, topbar, cards, buttons and inputs across the app switch to the light palette immediately (no reload needed) — confirms the CSS override block is wired correctly. Run `document.documentElement.setAttribute('data-theme', 'escuro')` to switch back.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.css frontend/src/routes/+layout.svelte
git commit -m "feat: add light theme CSS palette and data-theme application"
```

---

### Task 3: Frontend — topbar toggle button

**Files:**
- Modify: `frontend/src/lib/api.js` (add `atualizarTema` call)
- Modify: `frontend/src/routes/+layout.svelte` (icons, handler, button markup)

**Interfaces:**
- Consumes: `PUT /api/auth/tema` (Task 1), `$usuario` store (writable, supports `.update()`).
- Produces: `api.atualizarTema(tema)` — `(tema: 'claro'|'escuro') => Promise<{tema}>`, usable by any future settings UI.

- [ ] **Step 1: Add the API call**

Edit `frontend/src/lib/api.js`, add this line right after `me: () => request('/api/auth/me'),` (line 34):

```js
    atualizarTema: (tema) => request('/api/auth/tema', { method: 'PUT', body: JSON.stringify({ tema }) }),
```

- [ ] **Step 2: Add sun/moon icons**

Edit `frontend/src/routes/+layout.svelte`, add these two entries to the `I` object (after `chevR`, line 28):

```js
    sun:     `<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>`,
    moon:    `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`,
```

- [ ] **Step 3: Add the toggle handler**

Edit `frontend/src/routes/+layout.svelte`, add this function next to `trocarEmpresa` (after line 114):

```js
  async function alternarTema() {
    const novoTema = $usuario?.tema === 'claro' ? 'escuro' : 'claro';
    usuario.update(u => ({ ...u, tema: novoTema }));
    try { await api.atualizarTema(novoTema); }
    catch (e) { console.error('Erro ao salvar tema:', e); }
  }
```

- [ ] **Step 4: Add the button to the topbar**

Edit `frontend/src/routes/+layout.svelte`, add the button right before the `<div class="topbar-user">` block (before line 222):

```svelte
        <button
          class="icon-btn"
          on:click={alternarTema}
          aria-label={$usuario?.tema === 'claro' ? 'Mudar para tema escuro' : 'Mudar para tema claro'}
          title={$usuario?.tema === 'claro' ? 'Tema escuro' : 'Tema claro'}
        >
          {@html svg($usuario?.tema === 'claro' ? I.moon : I.sun)}
        </button>

```

- [ ] **Step 5: Restart the frontend and verify manually**

Run:

```bash
docker restart datahub_frontend
```

Open `http://localhost:3000`, log in. In the topbar, click the sun/moon button:
- Theme switches instantly (no reload).
- Open the browser Network tab: confirm a `PUT /api/auth/tema` request fires with the new value and returns 200.
- Reload the page: the chosen theme persists (confirms it's being read back from `/api/auth/me` on load, not just cached locally).
- Log out and log back in: theme is still applied (confirms DB persistence, not just the in-memory store).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/routes/+layout.svelte
git commit -m "feat: add theme toggle button to topbar"
```

---

### Task 4: Frontend — `ChartPanel.svelte` theme-aware colors

**Files:**
- Modify: `frontend/src/lib/components/ChartPanel.svelte`

**Interfaces:**
- Consumes: `$usuario.tema` from `frontend/src/lib/stores/auth.js`; CSS variables `--text`, `--muted`, `--border` (set on `<html>` by Task 2).

- [ ] **Step 1: Read live theme colors instead of hardcoded hex**

Replace the full contents of `frontend/src/lib/components/ChartPanel.svelte` with:

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';
  import { usuario } from '$lib/stores/auth.js';

  export let tipo = 'bar';
  export let dados = [];

  let container;
  let chart;

  const COLORS = ['#79c0ff','#f78166','#56d364','#d2a8ff','#ffa657','#39d353'];

  function corVar(nome) {
    return getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  }

  function buildOption(tipo, dados) {
    const labels = dados.map(d => d.label);
    const values = dados.map(d => Number(d.valor));
    const corTexto = corVar('--text');
    const corMuted = corVar('--muted');
    const corBorda = corVar('--border');

    if (tipo === 'chart_doughnut') {
      return {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', right: 10, textStyle: { color: corTexto } },
        series: [{
          type: 'pie', radius: ['45%', '70%'],
          data: dados.map((d, i) => ({ value: Number(d.valor), name: d.label, itemStyle: { color: COLORS[i % COLORS.length] } })),
          label: { color: corTexto }
        }]
      };
    }

    const isHorizontal = tipo === 'chart_bar_horizontal';
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: isHorizontal
        ? { type: 'value', axisLabel: { color: corMuted }, splitLine: { lineStyle: { color: corBorda } } }
        : { type: 'category', data: labels, axisLabel: { color: corMuted } },
      yAxis: isHorizontal
        ? { type: 'category', data: labels, axisLabel: { color: corMuted } }
        : { type: 'value', axisLabel: { color: corMuted }, splitLine: { lineStyle: { color: corBorda } } },
      series: [{
        type: tipo === 'chart_line' ? 'line' : 'bar',
        data: values,
        smooth: tipo === 'chart_line',
        itemStyle: { color: '#79c0ff' },
        areaStyle: tipo === 'chart_line' ? { color: 'rgba(121,192,255,.1)' } : undefined,
        barMaxWidth: 40,
      }]
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

- [ ] **Step 2: Verify manually**

Run:

```bash
docker restart datahub_frontend
```

Open a painel that includes a bar/line/doughnut chart widget (or `/` dashboard if one is configured there). Toggle the theme button:
- In dark theme: axis labels and legend text light-gray/white, gridlines subtle dark gray, all legible against the dark card background.
- In light theme: axis labels and legend text dark, gridlines light gray, all legible against the white card background.
- Series colors (bars/lines/doughnut segments) stay the same saturated colors in both themes.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/ChartPanel.svelte
git commit -m "feat: make ChartPanel colors theme-aware"
```

---

### Task 5: Frontend — `MapPanel.svelte` theme-aware tiles and marker color

**Files:**
- Modify: `frontend/src/lib/components/MapPanel.svelte`

**Interfaces:**
- Consumes: `$usuario.tema` from `frontend/src/lib/stores/auth.js`.

- [ ] **Step 1: Switch tile layer and marker stroke color by theme**

Replace the full contents of `frontend/src/lib/components/MapPanel.svelte` with:

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import { usuario } from '$lib/stores/auth.js';

  export let pontos = [];

  let container;
  let map;
  let markers = [];
  let leafletRef = null;
  let tileLayer = null;
  let temaAtual = null;

  const TILE_URLS = {
    escuro: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    claro:  'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
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
    tileLayer = L.tileLayer(TILE_URLS[tema] ?? TILE_URLS.escuro, { maxZoom: 19 }).addTo(map);
    temaAtual = tema;
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

<div bind:this={container} style="width:100%;height:300px;border-radius:8px;overflow:hidden;"></div>
```

- [ ] **Step 2: Verify manually**

Run:

```bash
docker restart datahub_frontend
```

Open a painel with a map widget. Toggle the theme button:
- Dark theme: CartoDB dark basemap, markers with a dark stroke.
- Light theme: CartoDB light basemap, markers with a white stroke, still legible.
- No overlapping/duplicated tile layers after switching a few times back and forth (only one basemap visible at a time).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/MapPanel.svelte
git commit -m "feat: make MapPanel tiles and marker color theme-aware"
```
