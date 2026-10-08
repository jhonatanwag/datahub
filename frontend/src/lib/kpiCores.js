// Cores de fábrica antigas dos KPIs (verde escuro do tema anterior e o grafite do padrão do banco).
// Elas ficaram gravadas por query; tratamos como "sem cor" pra o KPI seguir o tema atual.
// Cor personalizada de verdade (qualquer outra) continua valendo.
const FUNDOS_ANTIGOS = ['#2b5a45', '#161b22'];
const FONTES_ANTIGAS = ['#f3f8f5', '#e6edf3'];

const minusculo = (c) => (c ? String(c).toLowerCase() : null);

export function coresKpi(corFundo, corFonte) {
  const fundoAntigo = FUNDOS_ANTIGOS.includes(minusculo(corFundo));
  const fonteAntiga = FONTES_ANTIGAS.includes(minusculo(corFonte));
  return {
    fundo: fundoAntigo ? null : (corFundo || null),
    // a fonte só segue o tema quando o fundo também seguiu; senão pode ficar ilegível num fundo personalizado
    fonte: fundoAntigo && fonteAntiga ? null : (corFonte || null),
  };
}
