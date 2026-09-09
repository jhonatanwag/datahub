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
