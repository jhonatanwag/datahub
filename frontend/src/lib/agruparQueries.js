// Agrupa queries em duas camadas (grupo -> tipo) pro seletor de indicador do
// painel (<optgroup> só suporta um nível, então as duas camadas viram um
// único label "Grupo · tipo"). Sem grupo cadastrado cai em "Sem grupo",
// sempre por último.
export function agruparQueriesPorGrupoTipo(queries) {
  const mapa = new Map();
  for (const q of queries) {
    const grupo = q.grupo_nome || 'Sem grupo';
    const chave = `${grupo} · ${q.tipo}`;
    if (!mapa.has(chave)) mapa.set(chave, { grupo, chave, itens: [] });
    mapa.get(chave).itens.push(q);
  }
  return [...mapa.values()]
    .sort((a, b) => {
      if (a.grupo === 'Sem grupo' && b.grupo !== 'Sem grupo') return 1;
      if (b.grupo === 'Sem grupo' && a.grupo !== 'Sem grupo') return -1;
      return a.chave.localeCompare(b.chave, 'pt-BR', { sensitivity: 'base' });
    })
    .map(g => ({
      ...g,
      itens: [...g.itens].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { sensitivity: 'base' })),
    }));
}
