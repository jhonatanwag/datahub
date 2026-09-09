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
