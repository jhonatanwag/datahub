// Helpers puros do MapPanel: marcador com foto do tipo de equipamento e popup.

export function escaparHtml(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Ids (tip_veic_id) distintos dos pontos que pedem foto, em ordem crescente.
export function idsTiposComImagem(pontos) {
  const ids = new Set();
  for (const p of pontos ?? []) {
    const n = Number(p?.tip_veic_id);
    if (Number.isInteger(n) && n > 0) ids.add(n);
  }
  return [...ids].sort((a, b) => a - b);
}

export function htmlPopup(p) {
  let h = `<b>${escaparHtml(p.label)}</b>`;
  if (p.valor !== null && p.valor !== undefined && p.valor !== '') h += `<br>${escaparHtml(p.valor)}`;
  if (p.detalhe) h += `<br><span class="mp-detalhe">${escaparHtml(p.detalhe)}</span>`;
  return h;
}

// `url` é sempre um blob: gerado pelo próprio app; `borda` vem de constante do tema.
export function htmlMarcadorFoto(url, borda, tamanho = 44) {
  return `<div class="mp-foto" style="width:${tamanho}px;height:${tamanho}px;border-color:${borda}"><img src="${url}" alt=""></div>`;
}
