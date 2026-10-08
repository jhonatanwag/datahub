// Tokens de data usados nos valores padrão dos filtros ("hoje", "mes_atual_inicio"...).
const fmt = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

export function resolverToken(val, agora = new Date()) {
  if (!val) return '';
  const ano = agora.getFullYear(), mes = agora.getMonth() + 1;
  const ultimoDia = new Date(ano, mes, 0).getDate();
  const mesAnt = mes === 1 ? 12 : mes - 1;
  const anoAnt = mes === 1 ? ano - 1 : ano;
  const ultimoDiaMesAnt = new Date(anoAnt, mesAnt, 0).getDate();
  const tokens = {
    hoje: fmt(ano, mes, agora.getDate()),
    ontem: (() => { const d = new Date(agora); d.setDate(d.getDate() - 1); return fmt(d.getFullYear(), d.getMonth() + 1, d.getDate()); })(),
    mes_atual_inicio: fmt(ano, mes, 1),
    mes_atual_fim: fmt(ano, mes, ultimoDia),
    mes_anterior_inicio: fmt(anoAnt, mesAnt, 1),
    mes_anterior_fim: fmt(anoAnt, mesAnt, ultimoDiaMesAnt),
    ano_atual_inicio: fmt(ano, 1, 1),
    ano_atual_fim: fmt(ano, 12, 31),
  };
  return tokens[val] ?? val;
}

export function valoresIniciais(variaveis, agora = new Date()) {
  const v = {};
  variaveis.forEach(variavel => {
    if (variavel.tipo === 'date_range') {
      v[variavel.slug + '_inicio'] = resolverToken(variavel.valor_padrao_inicio || '', agora);
      v[variavel.slug + '_fim'] = resolverToken(variavel.valor_padrao_fim || '', agora);
    } else {
      v[variavel.slug] = resolverToken(variavel.valor_padrao || '', agora);
    }
  });
  return v;
}

export function resolverFiltros(filtros, agora = new Date()) {
  const r = {};
  for (const [k, v] of Object.entries(filtros ?? {})) r[k] = resolverToken(v, agora);
  return r;
}

// Chaves de parâmetro que uma variável produz (date_range gera duas).
export function chavesFiltro(variavel) {
  if (variavel.tipo === 'date_range') {
    return [
      { chave: variavel.slug + '_inicio', rotulo: `${variavel.nome} (início)` },
      { chave: variavel.slug + '_fim', rotulo: `${variavel.nome} (fim)` },
    ];
  }
  return [{ chave: variavel.slug, rotulo: variavel.nome }];
}
