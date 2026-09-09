# Relatório PDF no servidor + WhatsApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar o PDF do relatório no backend (headless Chrome renderizando a rota HTML que já existe), o botão passa a abrir o PDF direto inline, e um botão "WhatsApp" (só mobile) compartilha o PDF anexado via `navigator.share`. Inclui o fix de paginação do grid.

**Architecture:** Serviço interno novo `pdf-renderer` (Node + `http` nativo + Playwright). O backend ganha `GET /api/paineis/slug/{slug}/relatorio-pdf` que cria um token de troca de uso único (Redis 60s), monta a URL da rota de relatório com `?pdf_token=`, chama o renderer via `httpx`, e devolve `application/pdf` inline. A rota `/relatorio/painel/[slug]` troca o `pdf_token` por JWT no mount e sinaliza prontidão via `window.__RELATORIO_PRONTO__`. O frontend fetcha o blob e faz `window.open` / `navigator.share`.

**Tech Stack:** FastAPI + asyncpg + redis + httpx (já dep) · SvelteKit adapter-static SPA (JS puro) · Node 20 + Playwright 1.55 (`mcr.microsoft.com/playwright:v1.55.0-jammy`) · Docker Compose / EasyPanel.

**Spec:** `docs/superpowers/specs/2026-09-09-relatorio-pdf-servidor-design.md`

## Global Constraints

- **Frontend é JS puro, sem TypeScript.**
- **`npm run check` NÃO é gate** — o repo tem ~925 erros pré-existentes de "implicit any" (svelte-check com tsconfig num projeto JS). Uma task de frontend passa se o diff não adiciona categoria NOVA de erro nas linhas alteradas (erro de sintaxe, símbolo indefinido, import quebrado). Rodar `cd frontend && npm run check 2>&1 | tail -3` só pra conferir que o total não pulou dezenas.
- **Após editar `frontend/src/`**, `docker restart datahub_frontend`. Após editar `renderer/`, `docker compose -f docker-compose.dev.yml up -d --build pdf-renderer` (é build de imagem, sem bind-mount). `docker restart datahub_backend` funciona pra mudanças em `.py`.
- **Testes backend:** `docker exec datahub_backend python -m pytest tests/ -v`. Fixtures que criam `paineis` limpam com `hard_delete_painel` do `conftest.py`, nunca com o DELETE da API.
- **Login de teste:** `admin@datahub.local` / `admin123`, empresa `prats` (dados reais) ou `alpha`.
- **Segurança do token de troca:** TTL 60s, uso único (`GETDEL` atômico), mesmo padrão de `sso_exchange:` que já existe em `routes/auth.py`. Nunca colocar JWT em query string persistente nem em log.
- **Header do renderer:** `X-Renderer-Secret` — o renderer compara com `process.env.RENDERER_SECRET` e devolve 401 se não bater. Backend lê de `settings.RENDERER_SECRET`. Dev: `dev-secret` nos dois lados.
- **`page.pdf` do renderer:** sempre `{ printBackground: true, preferCSSPageSize: true, margin: { top:0, right:0, bottom:0, left:0 } }` — a orientação vem do `@page` da própria página (que a rota já seta a partir de `painel.impressao_orientacao` / heurística de colunas). Não passar `format`/`landscape`.
- **Sinal de prontidão:** a rota de relatório mantém `window.__RELATORIO_PRONTO__` (false até `pronto` virar true). O renderer espera por ele com timeout e é **best-effort** (se estourar, gera o PDF do jeito que está — o fallback de 12s da página normalmente já resolveu).
- **WhatsApp:** botão só renderiza quando `navigator.canShare?.({ files: [<File pdf>] })` é true. `AbortError` do `navigator.share` (usuário cancelou) é ignorado no catch.

---

## File Structure

**Serviço novo**
- `renderer/Dockerfile` — FROM playwright image, roda `server.mjs`.
- `renderer/package.json` — só `playwright` como dep.
- `renderer/server.mjs` — HTTP nativo, `POST /render` + `GET /health`.
- `renderer/.dockerignore` — `node_modules`, `*.log`.

**Backend**
- `backend/config/settings.py` — `RENDERER_URL`, `RENDERER_SECRET`, `RELATORIO_BASE_URL`.
- `backend/.env.dev` — `RENDERER_SECRET=dev-secret`.
- `backend/routes/auth.py` — `POST /api/auth/pdf-token/trocar` + `PdfTokenInput`.
- `backend/routes/paineis.py` — `GET /api/paineis/slug/{slug}/relatorio-pdf` + imports (`httpx`, `secrets`, `urllib.parse.urlencode`, `settings`, `get_redis`, `logger`).
- `backend/tests/test_relatorio_pdf.py` — **novo** (4 testes, `httpx` mockado).

**Frontend**
- `frontend/vite.config.js` — proxy `/api` → `http://backend:3001`.
- `frontend/src/lib/relatorioPdf.js` — **novo** (`abrirPdf`, `compartilharWhatsapp`, `podeCompartilhar`).
- `frontend/src/lib/api.js` — `trocarPdfToken`.
- `frontend/src/routes/+layout.svelte` — não redirecionar `/relatorio/…?pdf_token=` pro login.
- `frontend/src/routes/relatorio/painel/[slug]/+page.svelte` — remove toolbar, troca `pdf_token`, `window.__RELATORIO_PRONTO__`, fix do grid.
- `frontend/src/lib/relatorio/RelatorioCabecalho.svelte` — reverte offset `top: 44px`.
- `frontend/src/lib/relatorio/tema-relatorio.css` — remove `.relatorio-toolbar` + `scroll-padding-top`.
- `frontend/src/routes/painel/[slug]/+page.svelte` — botão "Abrir PDF" + "WhatsApp".
- `frontend/src/lib/components/DataTable.svelte` — `exportarPDF` via `relatorioPdf.js` + botão WhatsApp.
- `frontend/src/lib/components/DynamicTable.svelte` — idem.

**Infra / docs**
- `docker-compose.dev.yml` — serviço `pdf-renderer`; `frontend` com `VITE_API_URL=` vazio; `backend` com `RENDERER_SECRET`.
- `README.md` — 6º serviço no deploy + env vars.

---

## Task 1: Backend — token de troca + endpoint de PDF

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/.env.dev`
- Modify: `backend/routes/auth.py`
- Modify: `backend/routes/paineis.py` (imports linha 1-5; nova rota perto das outras `/slug/…`, ~linha 134)
- Test: `backend/tests/test_relatorio_pdf.py` (novo)

**Interfaces:**
- Produces:
  - `POST /api/auth/pdf-token/trocar` body `{ "pdf_token": str }` → `{ "token": "<jwt>" }` ou 401. Sem auth (chamador é o Chrome do renderer, ainda sem JWT).
  - `GET /api/paineis/slug/{slug}/relatorio-pdf?<filtros>&indicador=<id>` (`Depends(get_current_user)`, header `Authorization: Bearer`) → `200 application/pdf`, `Content-Disposition: inline; filename="Relatorio - <nome>.pdf"`. 401 sem auth, 404 slug inexistente, 502 se o renderer falhar.
  - `settings.RENDERER_URL` (default `http://pdf-renderer:4000`), `settings.RENDERER_SECRET` (default `""`), `settings.RELATORIO_BASE_URL` (default `http://frontend:3000`).
- Consumes: Redis `get_redis()`; `httpx` (já em `requirements.txt`).

- [ ] **Step 1: `settings.py` — 3 campos novos**

Em `backend/config/settings.py`, dentro da classe `Settings`, depois de `FRONTEND_URL`:

```python
    RENDERER_URL: str = "http://pdf-renderer:4000"
    RENDERER_SECRET: str = ""
    RELATORIO_BASE_URL: str = "http://frontend:3000"
```

Em `backend/.env.dev`, adicionar:

```
RENDERER_SECRET=dev-secret
```

- [ ] **Step 2: `routes/auth.py` — endpoint de troca (falhando)**

Escrever o teste primeiro. Criar `backend/tests/test_relatorio_pdf.py`:

```python
import asyncio
import pytest
from conftest import _connect_meta, hard_delete_painel


def _redis():
    import redis.asyncio as aioredis
    from config.settings import settings
    return aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


def test_trocar_pdf_token_uso_unico(client):
    async def _set():
        r = _redis()
        await r.setex("pdf_exchange:tok-teste-123", 60, "jwt-fake-abc")
        await r.aclose()
    asyncio.run(_set())

    r1 = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "tok-teste-123"})
    assert r1.status_code == 200
    assert r1.json()["token"] == "jwt-fake-abc"

    r2 = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "tok-teste-123"})
    assert r2.status_code == 401


def test_trocar_pdf_token_inexistente(client):
    r = client.post("/api/auth/pdf-token/trocar", json={"pdf_token": "nao-existe"})
    assert r.status_code == 401


@pytest.fixture
def painel_temp():
    async def _criar():
        conn = await _connect_meta()
        try:
            row = await conn.fetchrow(
                "INSERT INTO paineis (slug, nome) VALUES ('painel_pdf_teste', 'Painel PDF Teste') RETURNING id"
            )
            return row["id"]
        finally:
            await conn.close()
    pid = asyncio.run(_criar())
    yield pid
    hard_delete_painel(pid)


def test_relatorio_pdf_sem_auth_401(client, painel_temp):
    r = client.get("/api/paineis/slug/painel_pdf_teste/relatorio-pdf")
    assert r.status_code in (401, 403)


def test_relatorio_pdf_chama_renderer_e_devolve_pdf(client, auth_token, painel_temp, monkeypatch):
    import httpx

    class FakeResp:
        content = b"%PDF-1.4 fake"
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            assert kw["headers"]["X-Renderer-Secret"]  # segredo enviado
            assert "pdf_token=" in kw["json"]["url"]     # token na URL do renderer
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = client.get(
        "/api/paineis/slug/painel_pdf_teste/relatorio-pdf?data_inicio=2026-01-01",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == b"%PDF-1.4 fake"


def test_relatorio_pdf_502_quando_renderer_cai(client, auth_token, painel_temp, monkeypatch):
    import httpx

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            raise httpx.ConnectError("recusado")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = client.get(
        "/api/paineis/slug/painel_pdf_teste/relatorio-pdf",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 502
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `docker restart datahub_backend && sleep 3 && docker exec datahub_backend python -m pytest tests/test_relatorio_pdf.py -v`
Esperado: FAIL — `/api/auth/pdf-token/trocar` e `/api/paineis/slug/.../relatorio-pdf` dão 404 (rotas não existem).

- [ ] **Step 4: `routes/auth.py` — implementar a troca**

Em `backend/routes/auth.py`, adicionar (perto do fim, depois de `ssoTrocar`/`sso/trocar` ou junto dos outros models):

```python
class PdfTokenInput(BaseModel):
    pdf_token: str


@router.post("/pdf-token/trocar")
async def trocar_pdf_token(body: PdfTokenInput):
    redis = await get_redis()
    jwt_str = await redis.getdel(f"pdf_exchange:{body.pdf_token}")
    if not jwt_str:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return {"token": jwt_str}
```

- [ ] **Step 5: `routes/paineis.py` — imports + endpoint**

Linha 1 (imports): garantir `Response` já está (está) e adicionar no topo do arquivo:

```python
import secrets
import logging
from urllib.parse import urlencode
import httpx
from config.settings import settings
from config.redis import get_redis

logger = logging.getLogger("datahub")
```

(conferir se `logging`/`settings`/`get_redis` já não estão importados — se estiverem, não duplicar.)

Adicionar a rota logo **antes** de `@router.get("/slug/{slug}")` (~linha 134) pra não haver ambiguidade de match:

```python
@router.get("/slug/{slug}/relatorio-pdf")
async def relatorio_pdf(slug: str, request: Request, user=Depends(get_current_user)):
    rows = await query_meta(
        "SELECT nome FROM paineis WHERE slug = $1 AND ativo = true "
        "ORDER BY empresa_id NULLS LAST LIMIT 1",
        slug,
    )
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    nome = rows[0]["nome"]

    if user["role"] == "externo" and slug not in user.get("paineis_liberados", []):
        raise HTTPException(403, "Sem acesso a este painel")

    auth = request.headers.get("authorization", "")
    jwt_str = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not jwt_str:
        raise HTTPException(401, "Token ausente")

    token = secrets.token_hex(32)
    redis = await get_redis()
    await redis.setex(f"pdf_exchange:{token}", 60, jwt_str)

    qs = dict(request.query_params)
    qs["pdf_token"] = token
    url = f"{settings.RELATORIO_BASE_URL}/relatorio/painel/{slug}?{urlencode(qs)}"

    try:
        async with httpx.AsyncClient(timeout=45) as http:
            resp = await http.post(
                f"{settings.RENDERER_URL}/render",
                json={"url": url},
                headers={"X-Renderer-Secret": settings.RENDERER_SECRET},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"pdf-renderer falhou: {e}")
        raise HTTPException(502, "Falha ao gerar o PDF")

    filename = f"Relatorio - {nome}.pdf".replace("/", "-").replace('"', "")
    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
```

- [ ] **Step 6: Rodar e ver passar**

Run: `docker restart datahub_backend && sleep 3 && docker exec datahub_backend python -m pytest tests/test_relatorio_pdf.py -v`
Esperado: 5 PASS.

- [ ] **Step 7: Suíte inteira**

Run: `docker exec datahub_backend python -m pytest tests/ -q`
Esperado: verde (106 + 5 = 111 aprox).

- [ ] **Step 8: Commit**

```bash
git add backend/config/settings.py backend/.env.dev backend/routes/auth.py backend/routes/paineis.py backend/tests/test_relatorio_pdf.py
git commit -m "$(cat <<'EOF'
feat: endpoint de PDF do relatorio + token de troca pro renderer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 2: Serviço `pdf-renderer` + compose

**Files:**
- Create: `renderer/Dockerfile`, `renderer/package.json`, `renderer/server.mjs`, `renderer/.dockerignore`
- Modify: `docker-compose.dev.yml`

**Interfaces:**
- Consumes: `settings.RENDERER_URL` / `RENDERER_SECRET` do Task 1.
- Produces: serviço `pdf-renderer` na rede do compose, `POST /render {url}` (header `X-Renderer-Secret`) → `200 application/pdf` (bytes) ou `401`/`500`; `GET /health` → `200 ok`.

- [ ] **Step 1: `renderer/package.json`**

```json
{
  "name": "datahub-pdf-renderer",
  "private": true,
  "type": "module",
  "dependencies": {
    "playwright": "1.55.0"
  }
}
```

- [ ] **Step 2: `renderer/.dockerignore`**

```
node_modules
*.log
```

- [ ] **Step 3: `renderer/server.mjs`**

```js
import http from 'node:http';
import { chromium } from 'playwright';

const PORT = 4000;
const SECRET = process.env.RENDERER_SECRET || '';
const MAX_CONCURRENT = 2;

let browserPromise = null;
function getBrowser() {
  if (!browserPromise) {
    browserPromise = chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  }
  return browserPromise;
}

let ativos = 0;
const fila = [];
function acquire() {
  if (ativos < MAX_CONCURRENT) { ativos++; return Promise.resolve(); }
  return new Promise((res) => fila.push(res));
}
function release() {
  ativos--;
  const next = fila.shift();
  if (next) { ativos++; next(); }
}

async function render(url) {
  const browser = await getBrowser();
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page
      .waitForFunction(() => window.__RELATORIO_PRONTO__ === true, { timeout: 15000 })
      .catch(() => {});
    return await page.pdf({
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });
  } finally {
    await context.close();
  }
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    return res.end('ok');
  }
  if (req.method === 'POST' && req.url === '/render') {
    if (SECRET && req.headers['x-renderer-secret'] !== SECRET) {
      res.writeHead(401); return res.end('unauthorized');
    }
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 1e5) req.destroy(); });
    req.on('end', async () => {
      let url;
      try { url = JSON.parse(body).url; } catch { res.writeHead(400); return res.end('bad json'); }
      if (!url) { res.writeHead(400); return res.end('missing url'); }
      await acquire();
      const timeout = setTimeout(() => { try { res.destroy(); } catch {} }, 40000);
      try {
        const pdf = await render(url);
        res.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Length': pdf.length });
        res.end(pdf);
      } catch (e) {
        console.error('render falhou:', e.message);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ erro: e.message }));
      } finally {
        clearTimeout(timeout);
        release();
      }
    });
    return;
  }
  res.writeHead(404); res.end('not found');
});

server.listen(PORT, () => console.log(`pdf-renderer na porta ${PORT}`));
```

- [ ] **Step 4: `renderer/Dockerfile`**

```dockerfile
FROM mcr.microsoft.com/playwright:v1.55.0-jammy

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.mjs ./

EXPOSE 4000
CMD ["node", "server.mjs"]
```

- [ ] **Step 5: `docker-compose.dev.yml` — serviço + env do backend**

Adicionar o serviço (depois do `frontend`, antes de `volumes:`):

```yaml
  # ── PDF renderer (headless Chrome) ───────────────────────────
  pdf-renderer:
    build:
      context: ./renderer
    container_name: datahub_pdf_renderer
    restart: unless-stopped
    environment:
      - RENDERER_SECRET=dev-secret
    depends_on:
      - frontend
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:4000/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 5
```

O serviço `backend` já lê `./backend/.env.dev` (que ganhou `RENDERER_SECRET` no Task 1) — nada mais a fazer nele.

- [ ] **Step 6: Subir e testar**

```bash
docker compose -f docker-compose.dev.yml up -d --build pdf-renderer
sleep 40   # primeira vez baixa a imagem playwright (~1.7GB) — pode demorar
docker exec datahub_pdf_renderer node -e "require('http').get('http://localhost:4000/health',r=>{console.log(r.statusCode)})"
```
Esperado: `200`.

Testar `/render` com uma página pública simples (o relatório real é o Task 4):

```bash
docker exec datahub_backend python -c "
import httpx
r = httpx.post('http://pdf-renderer:4000/render', json={'url':'https://example.com'}, headers={'X-Renderer-Secret':'dev-secret'}, timeout=40)
print(r.status_code, r.headers.get('content-type'), len(r.content), r.content[:8])
"
```
Esperado: `200 application/pdf <n>000 b'%PDF-1.4'` (ou `%PDF-1.7`).

Testar o segredo:
```bash
docker exec datahub_backend python -c "
import httpx
print(httpx.post('http://pdf-renderer:4000/render', json={'url':'https://example.com'}, headers={'X-Renderer-Secret':'errado'}, timeout=10).status_code)
"
```
Esperado: `401`.

- [ ] **Step 7: Commit**

```bash
git add renderer/ docker-compose.dev.yml
git commit -m "$(cat <<'EOF'
feat: servico pdf-renderer (headless Chrome via Playwright)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 3: Frontend — proxy dev + `relatorioPdf.js` + `api.trocarPdfToken`

**Files:**
- Modify: `frontend/vite.config.js`
- Modify: `docker-compose.dev.yml` (serviço `frontend`: `VITE_API_URL=` vazio)
- Create: `frontend/src/lib/relatorioPdf.js`
- Modify: `frontend/src/lib/api.js`

**Interfaces:**
- Consumes: `GET /api/paineis/slug/{slug}/relatorio-pdf` e `POST /api/auth/pdf-token/trocar` (Task 1).
- Produces:
  - `relatorioPdf.js`: `abrirPdf(painelSlug, { indicador?, filtrosQuery? })` (Promise<void>), `compartilharWhatsapp(painelSlug, nome, opts)` (Promise<void>), `podeCompartilhar()` (bool).
  - `api.trocarPdfToken(pdf_token)` → `{ token }`.
  - Dev: `/api` relativo funciona via proxy do Vite (dev = prod).

- [ ] **Step 1: Vite proxy + `VITE_API_URL` vazio**

`frontend/vite.config.js`:

```js
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		host: true,
		proxy: {
			'/api': { target: 'http://backend:3001', changeOrigin: true }
		}
	}
});
```

`docker-compose.dev.yml`, serviço `frontend`, trocar:
```yaml
    environment:
      - VITE_API_URL=http://localhost:3001
```
por:
```yaml
    environment:
      - VITE_API_URL=
```

- [ ] **Step 2: `frontend/src/lib/relatorioPdf.js`**

```js
import { assetUrl } from '$lib/api.js';

function pdfUrl(painelSlug, { indicador, filtrosQuery } = {}) {
  const p = new URLSearchParams(filtrosQuery || '');
  if (indicador != null) p.set('indicador', indicador);
  return assetUrl(`/api/paineis/slug/${encodeURIComponent(painelSlug)}/relatorio-pdf?${p}`);
}

async function baixarBlob(painelSlug, opts) {
  const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
  const res = await fetch(pdfUrl(painelSlug, opts), {
    headers: tok ? { Authorization: `Bearer ${tok}` } : {},
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.blob();
}

export async function abrirPdf(painelSlug, opts) {
  const blob = await baixarBlob(painelSlug, opts);
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function podeCompartilhar() {
  try {
    if (!navigator.canShare) return false;
    const f = new File([new Blob()], 'x.pdf', { type: 'application/pdf' });
    return navigator.canShare({ files: [f] });
  } catch {
    return false;
  }
}

export async function compartilharWhatsapp(painelSlug, nome, opts) {
  const blob = await baixarBlob(painelSlug, opts);
  const file = new File([blob], `Relatorio - ${nome}.pdf`, { type: 'application/pdf' });
  try {
    await navigator.share({ files: [file], title: `Relatório — ${nome}` });
  } catch (e) {
    if (e && e.name === 'AbortError') return;
    throw e;
  }
}
```

- [ ] **Step 3: `api.js` — `trocarPdfToken`**

Em `frontend/src/lib/api.js`, junto de `ssoTrocar`:

```js
    trocarPdfToken: (pdf_token) =>
        request('/api/auth/pdf-token/trocar', { method: 'POST', body: JSON.stringify({ pdf_token }) }),
```

- [ ] **Step 4: Restart + smoke**

```bash
docker restart datahub_frontend && sleep 6
curl -s -o /dev/null -w "app: %{http_code}\n" http://localhost:3000/
curl -s -o /dev/null -w "api via proxy: %{http_code}\n" http://localhost:3000/api/health
cd frontend && npm run check 2>&1 | grep COMPLETED | tail -1
```
Esperado: `app: 200`, `api via proxy: 200` (o proxy do Vite repassa pro backend), check não pulou dezenas.

- [ ] **Step 5: Verificação manual — login ainda funciona**

Login `admin@datahub.local`/`admin123` no navegador → seleciona empresa → dashboard carrega (confirma que o `/api` relativo via proxy não quebrou o fluxo de auth).

- [ ] **Step 6: Commit**

```bash
git add frontend/vite.config.js docker-compose.dev.yml frontend/src/lib/relatorioPdf.js frontend/src/lib/api.js
git commit -m "$(cat <<'EOF'
feat: relatorioPdf.js (abrir PDF / compartilhar) + proxy /api no vite dev

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 4: Frontend — rota de relatório (toolbar, pdf_token, prontidão, fix do grid)

**Files:**
- Modify: `frontend/src/routes/relatorio/painel/[slug]/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte` (guard de auth)
- Modify: `frontend/src/lib/relatorio/RelatorioCabecalho.svelte`
- Modify: `frontend/src/lib/relatorio/tema-relatorio.css`

**Interfaces:**
- Consumes: `api.trocarPdfToken` (Task 3).
- Produces:
  - `window.__RELATORIO_PRONTO__` (bool) — o renderer (Task 2) espera por `=== true`.
  - A rota aceita `?pdf_token=<token>`: troca por JWT, seta `localStorage.token`, segue.
  - `/relatorio/…?pdf_token=` não é redirecionado pro `/login` pelo layout.
  - Sem `.relatorio-toolbar` no DOM.
  - Grid do painel pagina sem página em branco.

- [ ] **Step 1: `+layout.svelte` — não bounce a rota de relatório com pdf_token**

No `onMount` de auth (~linha 87-93), onde faz:
```js
    const path = $page.url.pathname;
    if (PUBLIC_ROUTES.includes(path)) return;
    const tok = localStorage.getItem('token');
    if (!tok) { goto('/login'); return; }
```
trocar por:
```js
    const path = $page.url.pathname;
    if (PUBLIC_ROUTES.includes(path)) return;
    const tok = localStorage.getItem('token');
    const relatorioComToken = path.startsWith('/relatorio/') && $page.url.searchParams.has('pdf_token');
    if (!tok && relatorioComToken) return;   // a própria página troca o pdf_token
    if (!tok) { goto('/login'); return; }
```

- [ ] **Step 2: Rota de relatório — troca do `pdf_token` + sinal de prontidão + toolbar fora**

Em `frontend/src/routes/relatorio/painel/[slug]/+page.svelte`:

No `<script>`, junto das `const params`:
```js
  const pdfToken = params.get('pdf_token');
```

No `onMount`, como **primeira coisa dentro do `try`** (antes de `const me = await api.me()`):
```js
      if (pdfToken) {
        const r = await api.trocarPdfToken(pdfToken);
        localStorage.setItem('token', r.token);
      }
```

Adicionar o bloco reativo de prontidão (junto dos outros `$:`):
```js
  $: if (typeof window !== 'undefined') window.__RELATORIO_PRONTO__ = pronto;
```

Remover o bloco da toolbar inteiro:
```svelte
<div class="relatorio-toolbar no-print">
  <strong>{tituloRelatorio}</strong>
  <span class="espaco"></span>
  {#if !pronto}<span class="preparando">Preparando relatório…</span>{/if}
  <button disabled={!pronto} on:click={() => window.print()}>Imprimir / Salvar PDF</button>
</div>
```

No `<style>`, remover:
```css
  .relatorio-toolbar { }
  .relatorio-toolbar .espaco { flex: 1; }
  .relatorio-toolbar .preparando { font-size: 13px; opacity: .9; }
```

- [ ] **Step 3: Fix de paginação do grid**

No mesmo arquivo, no `{:else}` do modo grid, o `<div class="grid-item" style="...">`:

trocar
```svelte
        <div class="grid-item" style="grid-column: {ind.coluna} / span {ind.col_span}; grid-row: {ind.linha}  / span {ind.row_span};">
```
por
```svelte
        <div class="grid-item" style="grid-column: {ind.coluna} / span {ind.col_span};">
```
(remove só o `grid-row`).

No `<style>`:
```css
  .painel-grid { display: grid; gap: 14px; grid-auto-flow: row dense; }
```
(adiciona `grid-auto-flow: row dense`).

- [ ] **Step 4: `RelatorioCabecalho.svelte` — reverter offset da toolbar**

No `<style>`, trocar:
```css
  @media screen { .rc { top: 44px; } }
  @media print { .rc { top: 0; } .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
```
por:
```css
  @media print { .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
```

- [ ] **Step 5: `tema-relatorio.css` — remover código morto da toolbar**

Remover o bloco:
```css
.relatorio-toolbar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 50;
  ...
}
.relatorio-toolbar button { ... }
.relatorio-toolbar button:disabled { ... }
```
e a linha `:root.relatorio-tema { scroll-padding-top: 48px; }` de dentro do `@media screen`.

- [ ] **Step 6: Restart + smoke**

```bash
docker restart datahub_frontend && sleep 6
curl -s -o /dev/null -w "rota relatorio: %{http_code}\n" http://localhost:3000/relatorio/painel/lanc_fichas
cd frontend && npm run check 2>&1 | grep COMPLETED | tail -1
grep -c "relatorio-toolbar" frontend/src/routes/relatorio/painel/\[slug\]/+page.svelte frontend/src/lib/relatorio/tema-relatorio.css
```
Esperado: `rota relatorio: 200`; `grep -c relatorio-toolbar` → `0` nos dois arquivos.

- [ ] **Step 7: Verificação end-to-end do fluxo do renderer**

Agora que Tasks 1+2+3+4 existem, testar o caminho completo:
```bash
# JWT de teste
ST=$(curl -s -X POST http://localhost:3001/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@datahub.local","senha":"admin123"}' | python -c "import sys,json;print(json.load(sys.stdin)['session_token'])")
JWT=$(curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa -H "Content-Type: application/json" -d "{\"session_token\":\"$ST\",\"empresa_id\":2}" | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /tmp/rel.pdf -w "pdf: %{http_code} %{size_download} bytes\n" "http://localhost:3001/api/paineis/slug/lanc_fichas/relatorio-pdf" -H "Authorization: Bearer $JWT"
head -c 8 /tmp/rel.pdf; echo
python -c "import re;d=open('/tmp/rel.pdf','rb').read();m=re.search(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)',d);print('MediaBox', m.group(1).decode(), 'x', m.group(2).decode())"
```
Esperado: `pdf: 200 <n> bytes`, começa com `%PDF`, MediaBox ~`595 x 842` (retrato). Se der 502 → ver logs do `pdf-renderer` (`docker logs datahub_pdf_renderer --tail 30`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/relatorio/ frontend/src/routes/+layout.svelte frontend/src/lib/relatorio/
git commit -m "$(cat <<'EOF'
feat: rota de relatorio troca pdf_token, sinaliza prontidao, sem toolbar; fix paginacao do grid

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 5: Frontend — botões "Abrir PDF" e "WhatsApp"

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`
- Modify: `frontend/src/lib/components/DataTable.svelte`
- Modify: `frontend/src/lib/components/DynamicTable.svelte`

**Interfaces:**
- Consumes: `abrirPdf`, `compartilharWhatsapp`, `podeCompartilhar` de `$lib/relatorioPdf.js` (Task 3).
- Produces: botões que geram/abrem o PDF via o endpoint; botão WhatsApp só quando `podeCompartilhar()`.

- [ ] **Step 1: `painel/[slug]/+page.svelte`**

Import (junto dos outros, ~linha 4):
```js
  import { abrirPdf, compartilharWhatsapp, podeCompartilhar } from '$lib/relatorioPdf.js';
```

No `<script>`, perto de `filtrosQuery`:
```js
  let gerandoPdf = false;
  const compartilhavel = podeCompartilhar();

  async function imprimirPainel() {
    gerandoPdf = true;
    try { await abrirPdf(slug, { filtrosQuery }); }
    catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
    finally { gerandoPdf = false; }
  }

  async function enviarWhatsapp() {
    gerandoPdf = true;
    try { await compartilharWhatsapp(slug, painel.nome, { filtrosQuery }); }
    catch (e) { alert('Erro: ' + e.message); }
    finally { gerandoPdf = false; }
  }
```
(remover a `function imprimirPainel()` antiga que fazia `window.open`.)

No `.painel-header-topo` (~linha 170-174), trocar o botão único por:
```svelte
      <div class="painel-header-topo">
        <h2>{painel.nome}</h2>
        <div class="painel-header-acoes">
          <button class="btn-ghost btn-imprimir" on:click={imprimirPainel} disabled={gerandoPdf}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="6 9 6 2 18 2 18 9"/>
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
              <rect x="6" y="14" width="12" height="8"/>
            </svg>
            {gerandoPdf ? 'Gerando…' : 'Abrir PDF'}
          </button>
          {#if compartilhavel}
            <button class="btn-ghost btn-imprimir" on:click={enviarWhatsapp} disabled={gerandoPdf}>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15l-1.3 4.7 4.8-1.3A10 10 0 1 0 12 2Zm5.8 14.2c-.2.7-1.4 1.3-2 1.4-.5.1-1.2.1-1.9-.1-.4-.1-1-.3-1.7-.6-3-1.3-4.9-4.3-5.1-4.5-.1-.2-1.2-1.5-1.2-2.9 0-1.4.7-2 1-2.3.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.3 0 .5l-.4.5-.3.3c-.1.1-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.2.1.4.1.5-.1l.7-.9c.2-.2.4-.2.6-.1l1.9.9c.2.1.4.2.5.3.1.2.1.7-.1 1.3Z"/></svg>
              WhatsApp
            </button>
          {/if}
        </div>
      </div>
```

No `<style>` (junto de `.painel-header-topo`):
```css
.painel-header-acoes { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-imprimir[disabled] { opacity: .55; cursor: default; }
```

- [ ] **Step 2: `DataTable.svelte`**

Import (~linha 2, junto de `baixarCSV`/`baixarXLSX`):
```js
  import { abrirPdf, compartilharWhatsapp, podeCompartilhar } from '$lib/relatorioPdf.js';
```

Trocar a `function exportarPDF()` (~linha 84-89) por:
```js
  let gerandoPdf = false;
  const compartilhavel = podeCompartilhar();

  async function exportarPDF() {
    if (!painelSlug || indicadorId == null) return;
    gerandoPdf = true;
    try { await abrirPdf(painelSlug, { indicador: indicadorId, filtrosQuery }); }
    catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
    finally { gerandoPdf = false; }
  }

  async function enviarWhatsapp() {
    if (!painelSlug || indicadorId == null) return;
    gerandoPdf = true;
    try { await compartilharWhatsapp(painelSlug, titulo, { indicador: indicadorId, filtrosQuery }); }
    catch (e) { alert('Erro: ' + e.message); }
    finally { gerandoPdf = false; }
  }
```

O bloco `{#if painelSlug} <button ...>🖨 PDF</button> {/if}` (~linha 165-168) vira:
```svelte
    {#if painelSlug}
    <button class="btn-export btn-export-pdf btn-sm" on:click={exportarPDF} disabled={dados.length === 0 || gerandoPdf}>
      {gerandoPdf ? 'Gerando…' : '🖨 PDF'}
    </button>
    {#if compartilhavel}
    <button class="btn-export btn-export-pdf btn-sm" on:click={enviarWhatsapp} disabled={dados.length === 0 || gerandoPdf}>
      WhatsApp
    </button>
    {/if}
    {/if}
```

- [ ] **Step 3: `DynamicTable.svelte`**

Mesmas 3 mudanças que o Step 2, adaptando: o import, o par `exportarPDF`/`enviarWhatsapp` (idênticos — `titulo` também existe como prop em `DynamicTable`), e o bloco do botão (`~linha 143-146`).

- [ ] **Step 4: Restart + check**

```bash
docker restart datahub_frontend && sleep 6
cd frontend && npm run check 2>&1 | grep COMPLETED | tail -1
grep -rn "window.open(\`/relatorio" frontend/src/ || echo "nenhum window.open pra rota de relatorio (esperado)"
```

- [ ] **Step 5: Verificação manual (Playwright/navegador)**

1. Login, painel `lanc_fichas` → "Abrir PDF" → spinner "Gerando…" → abre aba com o PDF renderizado (cabeçalho verde, sem página em branco no meio, rodapé).
2. Tabela → "🖨 PDF" → abre PDF só da tabela.
3. DevTools → emular iPhone → recarregar painel → botão "WhatsApp" aparece; no desktop não aparece.
4. Screenshot do PDF.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/painel/ frontend/src/lib/components/DataTable.svelte frontend/src/lib/components/DynamicTable.svelte
git commit -m "$(cat <<'EOF'
feat: botoes Abrir PDF e WhatsApp no painel e nas tabelas

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Task 6: Docs + walkthrough end-to-end

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README — deploy**

Na seção "Deploy no EasyPanel", tabela de serviços, adicionar a linha:
```
| `pdf-renderer` | `renderer/Dockerfile` | interna |
```
E um parágrafo depois da tabela:
> O `backend` fala com o `pdf-renderer` por `RENDERER_URL=http://pdf-renderer:4000`
> (o nome do serviço no EasyPanel tem que ser `pdf-renderer`). Env vars novas:
> - `backend` e `pdf-renderer`: `RENDERER_SECRET` — **o mesmo valor forte** nos dois.
> - `backend`: `RELATORIO_BASE_URL` — hostname interno do frontend. Em produção
>   o nginx do `frontend` escuta na porta 80, então `http://frontend` (sem
>   `:3000`). Confirmar no deploy.
> A imagem do `pdf-renderer` (`mcr.microsoft.com/playwright`) tem ~1.7 GB — a
> primeira build/pull demora. Se o deploy não reconstruir, mesma armadilha dos
> outros serviços (Forçar reconstrução / Stop-Start).

Nada de schema novo neste trabalho (sem `ALTER TABLE`).

- [ ] **Step 2: Suíte backend + check final**

```bash
docker exec datahub_backend python -m pytest tests/ -q
cd frontend && npm run check 2>&1 | grep COMPLETED | tail -1
```
Esperado: pytest verde; check ~mesma contagem.

- [ ] **Step 3: Walkthrough completo (headless, gerando PDFs de verdade)**

Reaproveitar a técnica dos PDFs de exemplo (playwright-core + Chrome do host), mas agora testando o **endpoint** (não o `window.print`):

1. `docker compose -f docker-compose.dev.yml up -d --build pdf-renderer frontend backend` — tudo no ar.
2. JWT via curl (login → selecionar-empresa, empresa `prats`).
3. `curl -o painel.pdf ".../api/paineis/slug/lanc_fichas/relatorio-pdf" -H "Authorization: Bearer $JWT"` → conferir `%PDF`, MediaBox retrato, **sem página em branco no meio** (fix do grid).
4. Setar `lanc_fichas` pra `impressao_orientacao='paisagem'` via PATCH → `curl` de novo → MediaBox paisagem (W>H) → reverter.
5. Pegar id de um indicador `table`/`table_dynamic` → `curl ".../relatorio-pdf?indicador=<id>"` → PDF só da tabela.
6. `curl` sem `Authorization` → 401.
7. `Read` os PDFs gerados pra conferir visual; `SendUserFile` pro usuário com legenda.
8. Reverter qualquer dado de teste alterado (endereço/CNPJ da Prats se setar, orientação do painel).

- [ ] **Step 4: Nota de memória**

Atualizar `project-datahub-overview.md`: seção da feature de impressão ganha um bloco sobre o `pdf-renderer` (serviço novo, `RENDERER_SECRET`/`RELATORIO_BASE_URL`, sem bind-mount → rebuild pra mudar), o endpoint `/api/paineis/slug/{slug}/relatorio-pdf`, o `pdf_token`, o botão WhatsApp (mobile only), e o fix do grid. Sem delta de schema. Atualizar a linha do `MEMORY.md`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: pdf-renderer no deploy do EasyPanel

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HyDYtfr52XK7JzHGwtUEop
EOF
)"
```

---

## Self-Review

**1. Spec coverage**

| Spec | Task |
|---|---|
| Serviço `pdf-renderer` (Node http nativo, Playwright, semáforo 2, `preferCSSPageSize`) | Task 2 (Steps 1-4) |
| `POST /render` + `X-Renderer-Secret` + `/health` | Task 2 (Step 3), testado Step 6 |
| `docker-compose` serviço + healthcheck | Task 2 (Step 5) |
| `settings.py` RENDERER_URL/SECRET/RELATORIO_BASE_URL | Task 1 (Step 1) |
| `GET /api/paineis/slug/{slug}/relatorio-pdf` (token 60s, chama renderer, inline) | Task 1 (Step 5) |
| `POST /api/auth/pdf-token/trocar` (GETDEL) | Task 1 (Step 4) |
| Testes backend (httpx mock, uso único, 401, 502) | Task 1 (Step 2) |
| `relatorioPdf.js` (abrirPdf, compartilharWhatsapp, podeCompartilhar) | Task 3 (Step 2) |
| `api.trocarPdfToken` | Task 3 (Step 3) |
| Vite proxy `/api` + `VITE_API_URL` vazio (dev = prod) | Task 3 (Step 1) |
| Rota relatório: remove toolbar | Task 4 (Step 2) |
| Rota relatório: troca `pdf_token` → localStorage | Task 4 (Step 2) |
| Rota relatório: `window.__RELATORIO_PRONTO__` | Task 4 (Step 2) |
| `+layout.svelte` não bounce `/relatorio/…?pdf_token=` | Task 4 (Step 1) |
| `RelatorioCabecalho` reverte `top: 44px` | Task 4 (Step 4) |
| `tema-relatorio.css` remove `.relatorio-toolbar` + scroll-padding | Task 4 (Step 5) |
| Fix paginação do grid (remove `grid-row`, `grid-auto-flow: dense`) | Task 4 (Step 3) |
| Botões "Abrir PDF" + "WhatsApp" no painel | Task 5 (Step 1) |
| Botões nas tabelas (`table`/`table_dynamic`) | Task 5 (Steps 2-3) |
| WhatsApp só se `navigator.canShare({files})` | Task 3 (Step 2 `podeCompartilhar`), usado Task 5 |
| README deploy 6º serviço + env vars | Task 6 (Step 1) |
| Nota de memória | Task 6 (Step 4) |
| Riscos (renderer grande, memória, networkidle, deploy) | Task 2 (Step 6 nota), Task 6 (Step 1) |

Sem lacunas. Nenhum `ALTER TABLE` — confirmado, feature não mexe em schema.

**2. Placeholder scan**

Sem "TBD"/"TODO". O `…` nos blocos de CSS a remover em Task 4 Step 5 refere-se ao conteúdo real do arquivo (o implementer lê e remove o bloco inteiro — a âncora `.relatorio-toolbar {` é única). Os SVGs de ícone são markup completo e válido.

**3. Type consistency**

- `abrirPdf(painelSlug, { indicador, filtrosQuery })` / `compartilharWhatsapp(painelSlug, nome, opts)` / `podeCompartilhar()` — assinaturas idênticas na definição (Task 3 Step 2) e nos 3 call sites (Task 5 Steps 1-3). ✓
- `api.trocarPdfToken(pdf_token)` → `{ token }` — definido Task 3 Step 3, consumido Task 4 Step 2 (`r.token`). ✓
- `window.__RELATORIO_PRONTO__` — escrito pela rota (Task 4 Step 2), lido pelo renderer `waitForFunction(() => window.__RELATORIO_PRONTO__ === true)` (Task 2 Step 3). Mesmo nome exato. ✓
- `X-Renderer-Secret` header — enviado pelo backend (Task 1 Step 5), checado pelo renderer via `req.headers['x-renderer-secret']` (Node lowercaseia headers) contra `process.env.RENDERER_SECRET` (Task 2 Step 3), valor `dev-secret` nos dois (Task 1 Step 1 `.env.dev`, Task 2 Step 5 compose). ✓
- `pdf_exchange:<token>` — `setex` no endpoint (Task 1 Step 5), `getdel` na troca (Task 1 Step 4), `setex` manual no teste (Task 1 Step 2). Mesmo prefixo. ✓
- Endpoint path `/api/paineis/slug/{slug}/relatorio-pdf` — backend (Task 1 Step 5), `relatorioPdf.js` `pdfUrl()` (Task 3 Step 2), testes (Task 1 Step 2). ✓
- `RELATORIO_BASE_URL` default `http://frontend:3000` (Task 1) bate com o hostname do serviço `frontend` no compose e a porta que o Vite dev serve (3000). ✓

Consistente.
