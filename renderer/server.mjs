import http from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { chromium } from 'playwright';

const PORT = 4000;
const SECRET = process.env.RENDERER_SECRET || '';
const MAX_CONCURRENT = 2;

if (!SECRET) {
  console.error('RENDERER_SECRET não definido — recusando iniciar');
  process.exit(1);
}
const BASE_URL = process.env.RELATORIO_BASE_URL || 'http://frontend';

function secretOk(h) {
  if (typeof h !== 'string' || h.length !== SECRET.length) return false;
  return timingSafeEqual(Buffer.from(h), Buffer.from(SECRET));
}

let browserPromise = null;
function getBrowser() {
  if (!browserPromise) {
    browserPromise = chromium
      .launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] })
      .then((b) => {
        b.on('disconnected', () => { browserPromise = null; });
        return b;
      })
      .catch((e) => { browserPromise = null; throw e; });
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

// A4 em px CSS @96dpi — o viewport tem que bater com a página final, senão o
// @media print da tela expande `.relatorio-pagina` até a largura do viewport e
// o page.pdf() escala tudo pra caber no A4 (relatório sai "com zoom out" e os
// gráficos ECharts, medidos na largura da tela, não preenchem o card).
const A4_RETRATO = { width: 794, height: 1123 };
const A4_PAISAGEM = { width: 1123, height: 794 };

async function render(url) {
  const browser = await getBrowser();
  const context = await browser.newContext({ viewport: A4_RETRATO });
  try {
    const page = await context.newPage();
    await page.emulateMedia({ media: 'print' });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page
      .waitForFunction(() => window.__RELATORIO_PRONTO__ === true, { timeout: 25000 })
      .catch(() => {});   // best-effort: página travada ainda gera PDF

    const paisagem = await page
      .evaluate(() => window.__RELATORIO_PAISAGEM__ === true)
      .catch(() => false);
    if (paisagem) {
      await page.setViewportSize(A4_PAISAGEM);
      // deixa o ResizeObserver do ECharts re-medir os gráficos (2 frames) antes
      // do snapshot do page.pdf(), que não espera callbacks assíncronos.
      await page.evaluate(
        () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
      );
    }

    return await page.pdf({
      printBackground: true,
      preferCSSPageSize: true,
      landscape: paisagem,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });
  } finally {
    await context.close();
  }
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    const b = browserPromise ? await browserPromise.catch(() => null) : null;
    const ok = !browserPromise || (b && b.isConnected());
    res.writeHead(ok ? 200 : 503, { 'Content-Type': 'text/plain' });
    return res.end(ok ? 'ok' : 'browser down');
  }
  if (req.method === 'POST' && req.url === '/render') {
    if (!secretOk(req.headers['x-renderer-secret'])) {
      res.writeHead(401); return res.end('unauthorized');
    }
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 1e5) req.destroy(); });
    req.on('end', async () => {
      let url;
      try { url = JSON.parse(body).url; } catch { res.writeHead(400); return res.end('bad json'); }
      if (!url) { res.writeHead(400); return res.end('missing url'); }
      if (!url.startsWith(BASE_URL + '/')) { res.writeHead(400); return res.end('url fora do escopo'); }
      await acquire();
      const timeout = setTimeout(() => { try { res.destroy(); } catch {} }, 55000);
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
