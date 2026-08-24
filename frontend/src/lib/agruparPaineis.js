// Agrupa painéis (menu lateral e dashboard) por `grupo_nome`, preservando a
// ordem de primeira ocorrência — como a lista já vem ordenada por
// `ordem_menu` do backend, isso posiciona cada grupo pelo menor ordem_menu
// entre seus painéis, sem precisar recalcular nada. "Sem grupo" sempre cai
// por último, mesmo que apareça antes na lista original.
export function agruparPaineisPorGrupo(paineis) {
  const mapa = new Map();
  for (const p of paineis) {
    const grupo = p.grupo_nome || 'Sem grupo';
    if (!mapa.has(grupo)) mapa.set(grupo, { grupo, itens: [] });
    mapa.get(grupo).itens.push(p);
  }
  const grupos = [...mapa.values()];
  const comGrupo = grupos.filter(g => g.grupo !== 'Sem grupo');
  const semGrupo = grupos.filter(g => g.grupo === 'Sem grupo');
  return [...comGrupo, ...semGrupo];
}
