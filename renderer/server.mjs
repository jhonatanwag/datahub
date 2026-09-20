import http from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { chromium } from 'playwright';

const PORT = 4000;
const SECRET = process.env.RENDERER_SECRET || '';
const MAX_CONCURRENT = 2;

// Limites de proteção — o PDF é gerado por um Chrome de verdade, cuja memória cresce de forma não
// linear com o tamanho do documento (medido: página de 128 mil px de altura -> page.pdf() de 280 s e
// >3 GB, sem nunca terminar). Tudo aqui existe pra falhar RÁPIDO e com mensagem, em vez de esgotar
// a RAM da máquina. Configuráveis por env sem rebuild.
const num = (v, d) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
const MAX_FILA = num(process.env.RENDER_MAX_FILA, 4);              // esperando vaga; acima disso recusa (503)
const RENDER_TIMEOUT_MS = num(process.env.RENDER_TIMEOUT_MS, 50000); // total por PDF; < timeout de 60 s do backend
const MAX_ALTURA_PX = num(process.env.RENDER_MAX_ALTURA_PX, 80000);  // ~ 100 páginas A4 paisagem
const MAX_NOS_DOM = num(process.env.RENDER_MAX_NOS_DOM, 250000);
const HEAP_JS_MB = num(process.env.RENDER_HEAP_JS_MB, 768);        // teto do heap V8 de cada aba

// Erro com status HTTP próprio: o backend repassa a mensagem ao usuário.
class RenderError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

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
      .launch({ args: ['--no-sandbox', '--disable-dev-shm-usage', `--js-flags=--max-old-space-size=${HEAP_JS_MB}`] })
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
  if (fila.length >= MAX_FILA) {
    return Promise.reject(new RenderError(503, 'Gerador de PDF ocupado. Aguarde alguns segundos e tente novamente.'));
  }
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

const esc = (s) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// Cabeçalho/rodapé que o Chrome repete em TODA página do PDF (dentro da margem
// de @page, sem colidir com o conteúdo). O cabeçalho GRANDE continua sendo
// conteúdo normal da página, aparece uma vez.
function headerTemplate(meta) {
  return `<style>#rh{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:8px;color:#8A968A;width:100%;box-sizing:border-box;padding:0 12mm;display:flex;justify-content:space-between;align-items:center;-webkit-print-color-adjust:exact}#rh b{color:#2E5E3E;font-weight:700}</style>
<div id="rh"><span><b>${esc(meta.titulo)}</b>${meta.empresa ? ' · ' + esc(meta.empresa) : ''}</span><span>${esc(meta.emitidoEm)}</span></div>`;
}
function footerTemplate() {
  return `<style>#rf{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:8px;color:#8A968A;width:100%;box-sizing:border-box;padding:4px 12mm 0;border-top:1px solid #E3E8E1;display:flex;justify-content:space-between;align-items:center;-webkit-print-color-adjust:exact}</style>
<div id="rf"><span>DataHub · GPA Analytics · Relatório gerado eletronicamente</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>`;
}

// `job.abort()` derruba de verdade o Chrome desse PDF (fecha o contexto; se ele não responder em 3 s,
// fecha o navegador inteiro). Sem isso o page.pdf() seguiria consumindo memória depois de o cliente/
// backend já terem desistido.
async function render(url, job) {
  const browser = await getBrowser();
  const context = await browser.newContext({ viewport: A4_RETRATO });
  let abortado = null;
  job.abort = (motivo) => {
    if (abortado) return;
    abortado = motivo;
    const nuclear = setTimeout(() => browser.close().catch(() => {}), 3000);
    context.close().catch(() => {}).finally(() => clearTimeout(nuclear));
  };
  const prazo = setTimeout(
    () => job.abort(new RenderError(504, 'Tempo esgotado ao gerar o PDF. Reduza o período ou os filtros.')),
    RENDER_TIMEOUT_MS,
  );
  try {
    const page = await context.newPage();
    await page.emulateMedia({ media: 'print' });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForFunction(() => window.__RELATORIO_PRONTO__ === true, { timeout: 25000 });

    const { paisagem, meta } = await page
      .evaluate(() => ({
        paisagem: window.__RELATORIO_PAISAGEM__ === true,
        meta: window.__RELATORIO_META__ || {},
      }))
      .catch(() => ({ paisagem: false, meta: {} }));

    if (paisagem) {
      await page.setViewportSize(A4_PAISAGEM);
      // deixa o ResizeObserver do ECharts re-medir os gráficos (2 frames) antes
      // do snapshot do page.pdf(), que não espera callbacks assíncronos.
      await page.evaluate(
        () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
      );
    }

    // Recusa ANTES de imprimir se o documento é grande demais — é o page.pdf() que estoura a memória.
    const { nos, altura } = await page.evaluate(() => ({
      nos: document.querySelectorAll('*').length,
      altura: document.documentElement.scrollHeight,
    }));
    if (altura > MAX_ALTURA_PX || nos > MAX_NOS_DOM) {
      throw new RenderError(
        413,
        `Relatório grande demais para gerar o PDF (${nos.toLocaleString('pt-BR')} elementos, ` +
        `${Math.round(altura / 1000)} mil px de altura). Reduza o período ou aplique mais filtros.`,
      );
    }

    return await page.pdf({
      printBackground: true,
      format: 'A4',
      landscape: paisagem,
      displayHeaderFooter: true,
      headerTemplate: headerTemplate(meta),
      footerTemplate: footerTemplate(),
      // topo/base reservam o cabeçalho/rodapé repetidos; lateral 0 pra o
      // conteúdo ser medido na largura cheia do A4 (o viewport = largura A4);
      // a folga lateral vem do padding do .relatorio-pagina na impressão.
      margin: { top: '16mm', bottom: '14mm', left: '0', right: '0' },
    });
  } catch (e) {
    throw abortado || e;   // se foi abortado (prazo/cliente), o erro relevante é o do abort, não "Target closed"
  } finally {
    clearTimeout(prazo);
    await context.close().catch(() => {});
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
      try { await acquire(); }
      catch (e) {
        res.writeHead(e.status || 503, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ erro: e.message }));
      }
      const job = { abort: () => {} };
      // cliente (backend) desistiu/caiu: derruba o Chrome em vez de deixá-lo trabalhando no vazio
      res.on('close', () => { if (!res.writableEnded) job.abort(new RenderError(499, 'cliente desconectou')); });
      try {
        const pdf = await render(url, job);
        res.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Length': pdf.length });
        res.end(pdf);
      } catch (e) {
        console.error('render falhou:', e.status || '', e.message);
        if (!res.writableEnded) {
          res.writeHead(e.status || 500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ erro: e.status ? e.message : 'Falha ao gerar o PDF.' }));
        }
      } finally {
        release();
      }
    });
    return;
  }
  res.writeHead(404); res.end('not found');
});

server.listen(PORT, () => console.log(`pdf-renderer na porta ${PORT}`));
