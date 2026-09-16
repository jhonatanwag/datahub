import { assetUrl } from '$lib/api.js';
import { podeCompartilhar } from '$lib/relatorioPdf.js';

const EXTENSOES_POR_TIPO = {
  'application/pdf': 'pdf',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'text/html': 'html',
  'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.ms-excel': 'xls',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
};

function nomeArquivo(titulo, contentType) {
  const agora = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const dataHora = `${agora.getFullYear()}${pad(agora.getMonth() + 1)}${pad(agora.getDate())}`
    + `_${pad(agora.getHours())}${pad(agora.getMinutes())}${pad(agora.getSeconds())}`;

  const base = (titulo || 'documento')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'documento';

  const tipo = (contentType || '').split(';')[0].trim();
  const ext = EXTENSOES_POR_TIPO[tipo] || 'pdf';

  return `${base}_${dataHora}.${ext}`;
}

async function baixarDocumento(painelSlug, indicadorId, valor) {
  const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
  const p = new URLSearchParams({ valor });
  const res = await fetch(
    assetUrl(`/api/paineis/slug/${encodeURIComponent(painelSlug)}/indicadores/${indicadorId}/imprimir?${p}`),
    { headers: tok ? { Authorization: `Bearer ${tok}` } : {} }
  );
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

function baixarBlobComoArquivo(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// Baixa o documento de impressão pelo backend (evita CORS e o nome fixo do
// servidor externo), renomeia com título + data/hora, e no celular abre a
// folha nativa de "abrir/compartilhar" via Web Share API.
export async function imprimirDocumento(painelSlug, indicadorId, valor, titulo) {
  const blob = await baixarDocumento(painelSlug, indicadorId, valor);
  const nome = nomeArquivo(titulo, blob.type);

  if (podeCompartilhar()) {
    try {
      const file = new File([blob], nome, { type: blob.type || 'application/octet-stream' });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: nome });
        return;
      }
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      // se o compartilhamento falhar por outro motivo, cai para o download normal
    }
  }

  baixarBlobComoArquivo(blob, nome);
}
