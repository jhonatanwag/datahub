# Relatório PDF gerado no servidor + compartilhar por WhatsApp — Design

Data: 2026-09-09
Status: aprovado (aguardando review do spec antes do plano)

## 1. Objetivo

Hoje o "PDF" do relatório é o diálogo de impressão do browser: o botão abre a
rota HTML `/relatorio/painel/[slug]` numa aba nova e o usuário ainda clica em
"Imprimir / Salvar PDF". Não existe arquivo PDF nenhum.

Este trabalho gera um **PDF de verdade no backend** (headless Chrome renderizando
a mesma rota HTML) e:

1. O botão passa a **abrir o PDF direto** (inline, aba nova com o visualizador
   de PDF do browser) — sem página intermediária, sem segundo clique.
2. Um botão **"Enviar por WhatsApp"** (só no celular) usa `navigator.share` pra
   mandar o PDF **anexado** pela folha de compartilhamento nativa.
3. Corrige a paginação do grid do painel (gráfico vazio → página em branco),
   que fica mais visível com PDF de verdade.

Vale pros dois modos: painel inteiro e tabela individual (`?indicador=`).

## 2. Decisões (brainstorming)

| Tema | Decisão |
|---|---|
| Onde gera o PDF | **Serviço novo `pdf-renderer`** (container separado), não na imagem do backend. |
| Stack do renderer | **Node com `http` nativo** (zero deps além do `playwright`), imagem base `mcr.microsoft.com/playwright`. |
| Auth do renderer → rota de relatório | **Token de troca de uso único** no Redis (60s), mesmo padrão de `sso_exchange`. Sem JWT em URL nem passado pro renderer. |
| UX do PDF | **Abre inline** no browser (aba nova via `blob:` URL). Não força download. |
| WhatsApp | **`navigator.share({files})`** — só aparece onde `navigator.canShare?.({files:[...]})` é true (celular). Escondido no desktop. Sem integração server-side (Cloud API fica fora). |
| Toolbar "Imprimir / Salvar PDF" da rota de relatório | **Removida.** O fluxo é 100% pelo endpoint. A rota HTML continua existindo (é o que o renderer carrega). |
| Prontidão observável | A rota seta `window.__RELATORIO_PRONTO__ = true`; o renderer espera por isso. |
| Fix de paginação do grid | **Incluído neste trabalho.** |

## 3. Arquitetura

```
[browser do usuário]
   botão "Abrir PDF" / "WhatsApp"
        │  fetch('/api/paineis/{id}/relatorio-pdf?<filtros>&indicador=<id>',
        │        { headers: { Authorization: Bearer <jwt> } })
        ▼
[backend  GET /api/paineis/{id}/relatorio-pdf]   (Depends(get_current_user))
   1. token = uuid4();  SETEX pdf_exchange:<token> 60 <jwt-do-header>
   2. url = f"{RELATORIO_BASE_URL}/relatorio/painel/{slug}?<filtros>&indicador=<id>&pdf_token=<token>"
   3. httpx.post(f"{RENDERER_URL}/render", json={"url": url},
                 headers={"X-Renderer-Secret": RENDERER_SECRET}, timeout=45)
   4. StreamingResponse(pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Relatorio - <nome>.pdf"'})
        │
        ▼
[pdf-renderer  POST /render]   (rede interna, valida X-Renderer-Secret)
   context = browser.newContext()
   page.goto(url, waitUntil="networkidle")
   page.waitForFunction("() => window.__RELATORIO_PRONTO__ === true", timeout=15000)  # + fallback
   pdf = page.pdf(printBackground=True, preferCSSPageSize=True, margin=0)
   context.close()
   → 200 application/pdf
        │
        ▼ (o Chrome do renderer, ao carregar a rota:)
[frontend  /relatorio/painel/[slug]?pdf_token=<token>]
   onMount: se pdf_token → POST /api/auth/pdf-token/trocar {pdf_token}
            → GETDEL pdf_exchange:<token> → devolve o jwt
            → localStorage.token = jwt → segue o fluxo normal (api.me, renderizarPainel…)
   quando `pronto` vira true → window.__RELATORIO_PRONTO__ = true
```

Topologia de rede: `pdf-renderer` é serviço **interno** (sem domínio público). O
Chrome dele alcança o `frontend` pela rede interna do compose/EasyPanel
(`RELATORIO_BASE_URL`). O SPA carregado nesse Chrome chama `/api/` relativo →
nginx do `frontend` faz proxy pro `backend` (igual a um usuário normal).

## 4. Serviço `pdf-renderer`

Diretório novo `renderer/`:

- `renderer/Dockerfile`
  ```dockerfile
  FROM mcr.microsoft.com/playwright:v1.55.0-jammy
  WORKDIR /app
  COPY package.json package-lock.json* ./
  RUN npm ci --omit=dev || npm install --omit=dev
  COPY server.mjs ./
  EXPOSE 4000
  CMD ["node", "server.mjs"]
  ```
- `renderer/package.json` — só `"playwright": "1.55.0"` como dependência.
- `renderer/server.mjs` — servidor HTTP nativo (`node:http`), um browser
  Chromium compartilhado (lazy-launch), semáforo de **2** contextos simultâneos,
  contexto novo por request e `context.close()` no `finally`.

  Contrato:
  - `POST /render` — body JSON `{ "url": string }`, header `X-Renderer-Secret`
    obrigatório (compara com `process.env.RENDERER_SECRET`; 401 se não bater).
    - `page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })`
    - `await page.waitForFunction(() => window.__RELATORIO_PRONTO__ === true,
      { timeout: 15000 }).catch(() => {})` — best-effort; se estourar, gera o
      PDF do jeito que está (o fallback de 12s da própria página normalmente já
      resolveu).
    - `const pdf = await page.pdf({ printBackground: true, preferCSSPageSize: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 } })`
    - responde `200` `application/pdf` com os bytes; `500` + `{erro}` em falha.
  - `GET /health` — `200 ok` (pro healthcheck do compose/EasyPanel).
  - Timeout total por request ~40s; erro → 500.

  `preferCSSPageSize: true` faz o `@page { size: A4 landscape }` da própria
  página decidir a orientação (que a rota já seta a partir de
  `painel.impressao_orientacao` / heurística de colunas). Fonte única de verdade.

- **`renderer/` NÃO tem bind-mount** no compose (é build de imagem). Mudança no
  `server.mjs` exige rebuild da imagem (`docker compose up -d --build pdf-renderer`).

## 5. Backend

### 5.1 `config/settings.py`

```python
    RENDERER_URL: str = "http://pdf-renderer:4000"
    RENDERER_SECRET: str = ""            # obrigatório em prod; em dev pode ser fixo
    RELATORIO_BASE_URL: str = "http://frontend:3000"   # hostname interno do frontend
```

`.env.dev` ganha `RENDERER_SECRET=dev-secret` (qualquer valor).

### 5.2 `routes/paineis.py` — `GET /slug/{slug}/relatorio-pdf`

Por slug (consistente com `buscarPainelPorSlug`; o front nem sempre tem o id).
Registrar a rota **antes** de qualquer `GET /slug/{slug}` genérica que exista,
ou usar um path que não colida (`/slug/{slug}/relatorio-pdf` não colide com
`/slug/{slug}`).

```python
@router.get("/slug/{slug}/relatorio-pdf")
async def relatorio_pdf(slug: str, request: Request, user=Depends(get_current_user)):
    painel_rows = await query_meta("SELECT slug, nome FROM paineis WHERE slug = $1 AND ativo = true", slug)
    if not painel_rows:
        raise HTTPException(404, "Painel não encontrado")
    nome = painel_rows[0]["nome"]

    # mesma autorização que renderizar_painel: externo checa paineis_liberados
    if user["role"] == "externo" and slug not in user["paineis_liberados"]:
        raise HTTPException(403, "Sem acesso a este painel")

    # token de troca de uso único — 60s — guarda o JWT do header
    auth = request.headers.get("authorization", "")
    jwt_str = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not jwt_str:
        raise HTTPException(401, "Token ausente")
    token = secrets.token_hex(32)
    redis = await get_redis()
    await redis.setex(f"pdf_exchange:{token}", 60, jwt_str)

    # repassa os filtros da query string (menos os de controle), + pdf_token
    qs = {k: v for k, v in request.query_params.items()}
    qs["pdf_token"] = token
    url = f"{settings.RELATORIO_BASE_URL}/relatorio/painel/{slug}?{urlencode(qs)}"

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{settings.RENDERER_URL}/render",
                json={"url": url},
                headers={"X-Renderer-Secret": settings.RENDERER_SECRET},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"pdf-renderer falhou: {e}")
        raise HTTPException(502, "Falha ao gerar o PDF")

    filename = f"Relatorio - {nome}.pdf".replace("/", "-")
    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
```

- `indicador` chega junto em `request.query_params` e é repassado pra `url` sem
  tratamento especial (a rota de relatório já lê `?indicador=`).
- **Não** precisa da trava de `codigo_usuario_externo` aqui — esse endpoint não
  chama `resolver_query` direto; quem chama é `renderizar_painel` (via a rota de
  relatório carregada no Chrome), que já tem a trava.

### 5.3 `routes/auth.py` — `POST /pdf-token/trocar`

```python
class PdfTokenInput(BaseModel):
    pdf_token: str

@router.post("/pdf-token/trocar")
async def trocar_pdf_token(body: PdfTokenInput):
    redis = await get_redis()
    jwt_str = await redis.getdel(f"pdf_exchange:{body.pdf_token}")
    if not jwt_str:
        raise HTTPException(401, "Token inválido ou expirado")
    return {"token": jwt_str}
```

Sem `Depends` — o chamador é o Chrome do renderer, que ainda não tem JWT. A
segurança é o token de 60s + uso único (GETDEL atômico), igual ao
`sso_exchange`.

### 5.4 `requirements.txt`

Nada novo — `httpx==0.27.0` já está lá.

### 5.5 Testes backend

`backend/tests/test_relatorio_pdf.py`:

- `test_relatorio_pdf_gera_token_e_chama_renderer` — mocka o `httpx.AsyncClient`
  (monkeypatch) pra devolver bytes fake; confere que a resposta é
  `application/pdf`, `Content-Disposition: inline`, e que uma chave
  `pdf_exchange:*` foi criada no Redis com o JWT.
- `test_trocar_pdf_token_uso_unico` — cria a chave manualmente, chama
  `/api/auth/pdf-token/trocar` → devolve o JWT; segunda chamada → 401.
- `test_relatorio_pdf_404_painel_inexistente`.
- `test_relatorio_pdf_502_quando_renderer_cai` — mock que levanta `httpx.HTTPError`.

O renderer em si (Playwright) **não** entra na suíte pytest — é testado no
walkthrough manual (Task de verificação).

## 6. Frontend

### 6.1 `$lib/relatorioPdf.js` (novo)

```js
import { assetUrl } from '$lib/api.js';

function pdfUrl(painelSlug, { indicador, filtrosQuery } = {}) {
  const p = new URLSearchParams(filtrosQuery || '');
  if (indicador != null) p.set('indicador', indicador);
  return assetUrl(`/api/paineis/slug/${painelSlug}/relatorio-pdf?${p}`);   // ver nota
}

async function baixarBlob(painelSlug, opts) {
  const tok = localStorage.getItem('token');
  const res = await fetch(pdfUrl(painelSlug, opts), {
    headers: tok ? { Authorization: `Bearer ${tok}` } : {},
  });
  if (!res.ok) throw new Error((await res.text().catch(() => '')) || `HTTP ${res.status}`);
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
    return !!navigator.canShare &&
      navigator.canShare({ files: [new File([new Blob()], 'x.pdf', { type: 'application/pdf' })] });
  } catch { return false; }
}

export async function compartilharWhatsapp(painelSlug, nome, opts) {
  const blob = await baixarBlob(painelSlug, opts);
  const file = new File([blob], `Relatorio - ${nome}.pdf`, { type: 'application/pdf' });
  await navigator.share({ files: [file], title: `Relatório — ${nome}` });
}
```

Endpoint por slug: `/api/paineis/slug/{slug}/relatorio-pdf` (ver 5.2).

### 6.2 `painel/[slug]/+page.svelte`

- Importa `abrirPdf`, `compartilharWhatsapp`, `podeCompartilhar`.
- `let gerandoPdf = false; const compartilhavel = podeCompartilhar();`
- `imprimirPainel()` deixa de fazer `window.open('/relatorio/...')` e passa a:
  ```js
  async function imprimirPainel() {
    gerandoPdf = true;
    try { await abrirPdf(slug, { filtrosQuery }); }
    catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
    finally { gerandoPdf = false; }
  }
  ```
- Botão "Imprimir" vira "Abrir PDF" com estado `{gerandoPdf ? 'Gerando…' : 'Abrir PDF'}`, `disabled={gerandoPdf}`.
- Botão novo, ao lado, só se `compartilhavel`:
  ```svelte
  {#if compartilhavel}
    <button class="btn-ghost btn-imprimir" on:click={enviarWhatsapp} disabled={gerandoPdf}>
      <svg …whatsapp…/> WhatsApp
    </button>
  {/if}
  ```
  `enviarWhatsapp()` = `compartilharWhatsapp(slug, painel.nome, { filtrosQuery })` com o mesmo try/catch (ignora `AbortError` — usuário cancelou a share sheet).

### 6.3 `DataTable.svelte` / `DynamicTable.svelte`

O botão `🖨 PDF` (dentro de `{#if painelSlug}`) troca `exportarPDF()`:
```js
import { abrirPdf, compartilharWhatsapp, podeCompartilhar } from '$lib/relatorioPdf.js';
let gerandoPdf = false;
const compartilhavel = podeCompartilhar();
async function exportarPDF() {
  gerandoPdf = true;
  try { await abrirPdf(painelSlug, { indicador: indicadorId, filtrosQuery }); }
  catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
  finally { gerandoPdf = false; }
}
```
Botão: `{gerandoPdf ? 'Gerando…' : '🖨 PDF'}`, `disabled={dados.length === 0 || gerandoPdf}`.
Botão WhatsApp ao lado, `{#if compartilhavel}`, chamando `compartilharWhatsapp(painelSlug, titulo, { indicador: indicadorId, filtrosQuery })`.

### 6.4 `relatorio/painel/[slug]/+page.svelte`

- **Remove** o bloco `<div class="relatorio-toolbar no-print">…</div>` inteiro e os
  estilos `.relatorio-toolbar*` do `<style>`.
- **Remove** a regra `.relatorio-toolbar {…}` de `tema-relatorio.css` (adicionada
  na feature anterior) — vira código morto. (o `{ top: 44px }` do
  `RelatorioCabecalho.svelte` `@media screen` também some — a faixa volta pro
  topo na tela; ver 6.5.)
- No `<script>`, ler `pdf_token`:
  ```js
  const pdfToken = params.get('pdf_token');
  ```
  No `onMount`, **antes** de `api.me()`:
  ```js
  if (pdfToken) {
    try {
      const r = await api.trocarPdfToken(pdfToken);
      localStorage.setItem('token', r.token);
    } catch (e) { erro = 'Token de PDF inválido'; carregando = false; return; }
  }
  ```
- Sinal de prontidão pro renderer: bloco reativo
  ```js
  $: if (typeof window !== 'undefined') window.__RELATORIO_PRONTO__ = pronto;
  ```
  (fica `false` até `pronto` virar `true`; o `setTimeout` de 12s continua como
  rede de segurança).
- `api.js`: `trocarPdfToken: (pdf_token) => request('/api/auth/pdf-token/trocar', { method: 'POST', body: JSON.stringify({ pdf_token }) })`.
- Um humano abrindo `/relatorio/painel/<slug>` direto (sem `pdf_token`) ainda vê
  o relatório renderizado; sem toolbar, usa o Ctrl+P do browser se quiser. É
  caminho degradado aceitável.

### 6.5 `RelatorioCabecalho.svelte`

Reverter o offset da toolbar (feature anterior): trocar
```css
  @media screen { .rc { top: 44px; } }
  @media print { .rc { top: 0; } … }
```
por
```css
  @media print { .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
```
(a faixa é `top: 0` sempre; sem toolbar não há o que descontar).

`tema-relatorio.css`: remover o bloco `.relatorio-toolbar {…}` e o
`:root.relatorio-tema { scroll-padding-top: 48px; }` do `@media screen`.

## 7. Fix de paginação do grid

**Problema:** `grid-row: {linha} / span {row_span}` força o item a ocupar N
tracks de linha independente do conteúdo. Gráfico vazio (0 linhas de dado) num
item com `row_span` alto vira uma caixa gigante; com `break-inside: avoid` o
próximo item é empurrado inteiro pra página seguinte, deixando meia página em
branco.

**Fix** (no `relatorio/painel/[slug]/+page.svelte`, só o modo grid):

- Manter `grid-column: {coluna} / span {col_span}` (preserva a disposição
  horizontal que o usuário quis).
- **Remover** o `grid-row: {linha} / span {row_span}` do `style` inline do
  `.grid-item` — as linhas passam a se dimensionar pelo conteúdo.
- `.painel-grid { grid-auto-flow: row dense; }` — empacota, evitando buracos.
- `ChartPanel` no relatório: garantir que o container não estica além dos
  `260px` fixos que ele já tem (sem `row_span` puxando, o item fica na altura do
  chart — ok).
- `.grid-item { break-inside: avoid; }` continua (evita cortar um card no meio).
- `@media print { .grid-item { break-inside: avoid; } .painel-grid { gap: 10px; } }`.

Resultado: o grid mantém colunas/spans, mas as linhas colapsam pro conteúdo e a
paginação flui sem páginas em branco. A ordem visual segue `ORDER BY pi.linha,
pi.coluna` que `renderizar_painel` já devolve.

> Alternativa considerada e **rejeitada**: linearizar tudo (1 indicador por
> bloco full-width). O usuário pediu explicitamente "preserva o grid" na feature
> anterior; remover só o `grid-row` mantém a intenção e resolve o problema.

## 8. Infra / deploy

### 8.1 `docker-compose.dev.yml`

```yaml
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

`backend` ganha no `environment`/`.env.dev`: `RENDERER_SECRET=dev-secret`
(mesmo valor). `RENDERER_URL` e `RELATORIO_BASE_URL` usam os defaults do
settings (`http://pdf-renderer:4000`, `http://frontend:3000`).

### 8.2 Dev: `/api` relativo

`VITE_API_URL=http://localhost:3001` (no compose dev) quebra dentro do Chrome do
renderer. Fix pra alinhar dev com prod:

- `docker-compose.dev.yml` serviço `frontend`: trocar
  `- VITE_API_URL=http://localhost:3001` por `- VITE_API_URL=` (vazio).
- `frontend/vite.config.js`: adicionar proxy dev:
  ```js
  export default defineConfig({
    plugins: [sveltekit()],
    server: {
      host: true,
      proxy: { '/api': 'http://backend:3001' }
    }
  });
  ```
  (o Vite dev server passa a repassar `/api` pro backend, igual ao nginx em
  prod). Um usuário em `localhost:3000` também funciona — o proxy roda no
  container do frontend, que resolve `backend`.

### 8.3 `README.md` — seção "Deploy no EasyPanel"

- Tabela de serviços: linha nova
  `| pdf-renderer | renderer/Dockerfile | interna |`.
- Nota: `pdf-renderer` não precisa de domínio; o `backend` fala com ele por
  `RENDERER_URL=http://pdf-renderer:4000` (nome do serviço no EasyPanel tem que
  ser `pdf-renderer`).
- Env vars novas no `backend`: `RENDERER_SECRET` (gerar um valor forte, mesmo
  nos dois serviços), `RENDERER_URL` (default ok), `RELATORIO_BASE_URL` (em prod
  = `http://frontend` — sem porta, o nginx escuta na 80; confirmar no deploy).
- Env var no `pdf-renderer`: `RENDERER_SECRET` (igual ao do backend).
- Ordem de deploy: `frontend` antes de `pdf-renderer` (o healthcheck do renderer
  não depende do frontend, mas o `depends_on` sim).

### 8.4 `renderer/.dockerignore`

`node_modules`, `*.log`.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Imagem `mcr.microsoft.com/playwright` é grande (~1.7 GB) | É o custo de ter Chrome + libs sem dor de cabeça. Só puxa uma vez; o layer fica em cache. VPS precisa de espaço em disco. |
| Memória: Chrome + contextos (~150 MB base + ~80 MB/contexto) | Semáforo de 2 contextos; container com ~1 GB de limite. Documentar. |
| `networkidle` pode nunca disparar (mapa com tiles, polling) | `timeout: 30000` no `goto` + `waitForFunction` best-effort + fallback de 12s da própria página. Pior caso: PDF sai do jeito que está aos 15s. |
| `preferCSSPageSize` + `@page` em `<svelte:head>` | Testado antes com `page.pdf()`; o `<style>` no head é aplicado. Confirmar no walkthrough (retrato E paisagem). |
| Chrome do renderer não alcança o `frontend` | `RELATORIO_BASE_URL` = hostname interno; healthcheck + walkthrough confirmam. Em dev o `depends_on` garante ordem. |
| Deploy no EasyPanel não reconstrói o `pdf-renderer` | Mesma armadilha dos outros serviços — "Forçar reconstrução" / Stop-Start. Documentar. |
| JWT de 480 min guardado 60s no Redis | Uso único (GETDEL), TTL 60s, rede interna. Aceitável — é o mesmo nível do `sso_exchange`. |
| `navigator.share` cancelado pelo usuário lança `AbortError` | `catch` ignora `AbortError` explicitamente. |
| Desktop sem `navigator.canShare({files})` | Botão WhatsApp só renderiza se `podeCompartilhar()` — some no desktop. |
| Grid fix muda o visual de painéis existentes | Só remove `grid-row` (altura), mantém colunas/spans. Walkthrough compara antes/depois num painel real. |

## 10. Testes

- **Backend:** `backend/tests/test_relatorio_pdf.py` (4 testes, `httpx` mockado) — ver 5.5.
- **Frontend:** `npm run check` sem categoria nova de erro (repo tem ~925 pré-existentes).
- **Walkthrough manual (Playwright/headless):**
  - `docker compose -f docker-compose.dev.yml up -d --build pdf-renderer` + `frontend` (proxy novo) + `backend`.
  - Login admin, empresa `prats`.
  - Painel `lanc_fichas` → "Abrir PDF" → abre aba com o PDF; conferir cabeçalho, sem página em branco no meio (fix do grid), rodapé.
  - Painel em `impressao_orientacao='paisagem'` → PDF em paisagem (`MediaBox` W>H).
  - Tabela → "🖨 PDF" → PDF só da tabela, `RELAÇÃO DE DADOS`, todas as linhas.
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/api/paineis/slug/lanc_fichas/relatorio-pdf` **sem** Authorization → 401.
  - Emular mobile (DevTools) → botão "WhatsApp" aparece; desktop → não aparece.
  - `docker exec datahub_backend python -m pytest tests/ -v` — verde.
- Screenshots/PDF de exemplo pro usuário.

## 11. Fora de escopo

- Envio server-side pelo WhatsApp Cloud API (número → mensagem automática).
- Link público/tokenizado do relatório (compartilhar por link sem login).
- Fila/assincronismo (job + polling) — o endpoint é síncrono (spinner ~2-5s).
- Cache de PDF (cada clique regenera).
- Reaproveitar o `pdf-renderer` pra outros PDFs (relatório mensal do `worker` etc.) — possível depois, não agora.
