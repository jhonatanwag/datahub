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
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.clone().json();
      if (j && j.detail) msg = j.detail;
    } catch {
      const t = await res.text().catch(() => '');
      if (t) msg = t;
    }
    throw new Error(msg);
  }
  return res.blob();
}

export async function abrirPdf(painelSlug, opts) {
  const win = window.open('', '_blank');   // dentro do gesto do usuário
  try {
    const blob = await baixarBlob(painelSlug, opts);
    const url = URL.createObjectURL(blob);
    if (win) {
      win.opener = null;
      win.location = url;
    } else {
      const a = document.createElement('a');
      a.href = url;
      a.download = `Relatorio - ${painelSlug}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    if (win) win.close();
    throw e;
  }
}

export function podeCompartilhar() {
  try {
    if (!navigator.canShare) return false;
    if (!window.matchMedia?.('(pointer: coarse)').matches) return false;  // desktop → esconde
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
