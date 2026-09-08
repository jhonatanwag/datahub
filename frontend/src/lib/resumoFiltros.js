// YYYY-MM-DD → DD/MM/YYYY
export function fmtData(val) {
  if (!val || val.length !== 10) return val ?? '';
  const [y, m, d] = val.split('-');
  return `${d}/${m}/${y}`;
}

// Resumo legível dos filtros ativos de um painel: [{nome, valor}].
// Extraído de /painel/[slug]/+page.svelte pra ser reusado pela rota de relatório.
export function resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel = {}) {
  return variaveis.flatMap(v => {
    if (v.tipo === 'date_range') {
      const ini = filtrosAtivos[v.slug + '_inicio'];
      const fim = filtrosAtivos[v.slug + '_fim'];
      if (!ini && !fim) return [];
      return [{ nome: v.nome, valor: `${fmtData(ini) || '—'} até ${fmtData(fim) || '—'}` }];
    }
    const val = filtrosAtivos[v.slug];
    if (!val) return [];

    if (v.tipo === 'select' || v.tipo === 'multiselect') {
      const opcoes = opcoesPorVariavel[v.slug] || [];
      const labels = String(val).split(',').map(id => {
        const opt = opcoes.find(o => String(o.valor) === id);
        return opt ? opt.label : id;
      });
      return [{ nome: v.nome, valor: labels.join(', ') }];
    }

    return [{ nome: v.nome, valor: String(val) }];
  });
}
