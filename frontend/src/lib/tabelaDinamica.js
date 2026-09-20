// Lógica pura do table_dynamic (agrupamento em árvore + pivô de colunas).
// Fica fora do .svelte pra ser testável com `node --test` e reaproveitada
// pela exportação (exportTable.js).

export const FUNCOES = {
  soma:     vals => vals.reduce((a, b) => a + b, 0),
  contagem: vals => vals.length,
  media:    vals => vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
  minimo:   vals => vals.length ? Math.min(...vals) : 0,
  maximo:   vals => vals.length ? Math.max(...vals) : 0,
};

const ROTULO_TOTAL = 'Total Geral';

function agregar(linhas, ag) {
  // Sem agregação configurada o pivô simplesmente conta linhas.
  if (!ag) return linhas.length;
  const valores = linhas.map(r => Number(r[ag.coluna])).filter(v => !Number.isNaN(v));
  return (FUNCOES[ag.funcao] ?? FUNCOES.soma)(valores);
}

export function calcularAgregacoes(linhas, agregacoes) {
  return agregacoes.map(ag => ({ coluna: ag.coluna, label: ag.label, valor: agregar(linhas, ag) }));
}

const rotuloDe = valor => (valor === null || valor === undefined ? '—' : String(valor));

// Descobre as colunas do pivô (valores distintos de `cfg.coluna`), na ordem
// de `cfg.ordem_coluna` (menor valor por grupo) ou, sem ela, na de aparição.
// Devolve null quando não há pivô configurado.
export function montarPivot(dados, cfg, agregacoes) {
  if (!cfg?.coluna) return null;

  const ordemDoValor = new Map(); // valor do pivô -> menor valor da coluna de ordem
  for (const linha of dados) {
    const v = linha[cfg.coluna];
    if (!ordemDoValor.has(v)) ordemDoValor.set(v, linha[cfg.ordem_coluna]);
    else if (cfg.ordem_coluna && linha[cfg.ordem_coluna] < ordemDoValor.get(v)) {
      ordemDoValor.set(v, linha[cfg.ordem_coluna]);
    }
  }

  let valores = [...ordemDoValor.keys()];
  if (cfg.ordem_coluna) {
    valores = valores.sort((a, b) => {
      const oa = ordemDoValor.get(a), ob = ordemDoValor.get(b);
      return oa < ob ? -1 : oa > ob ? 1 : 0;
    });
  }

  const cabecalhos = valores.map(v => ({ label: rotuloDe(v), semRotulo: true }));
  if (cfg.total) cabecalhos.push({ label: ROTULO_TOTAL, semRotulo: true });

  return {
    coluna: cfg.coluna,
    ordemColuna: cfg.ordem_coluna ?? null,
    total: !!cfg.total,
    valores,
    cabecalhos,
    agregacao: agregacoes[0] ?? null,
  };
}

// Uma célula por valor do pivô (+ Total Geral) pro conjunto de linhas dado.
// Mês sem ocorrência fica null pra a tela mostrar vazio em vez de 0.
function celulasDoPivot(linhas, pivot) {
  const celulas = pivot.valores.map((v, i) => {
    const doValor = linhas.filter(r => r[pivot.coluna] === v);
    return {
      coluna: pivot.agregacao?.coluna,
      label: pivot.cabecalhos[i].label,
      valor: doValor.length ? agregar(doValor, pivot.agregacao) : null,
      semRotulo: true,
    };
  });
  if (pivot.total) {
    celulas.push({
      coluna: pivot.agregacao?.coluna,
      label: ROTULO_TOTAL,
      valor: agregar(linhas, pivot.agregacao),
      semRotulo: true,
    });
  }
  return celulas;
}

export function construirArvore(linhas, nivel, agrupamentos, agregacoes, pivot = null) {
  if (nivel >= agrupamentos.length) return { folha: true, linhas };
  const coluna = agrupamentos[nivel];
  const grupos = new Map();
  for (const linha of linhas) {
    const chave = linha[coluna];
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(linha);
  }
  const arvore = {
    folha: false,
    grupos: [...grupos.entries()].map(([valor, linhasGrupo]) => ({
      valor,
      agregados: pivot ? celulasDoPivot(linhasGrupo, pivot) : calcularAgregacoes(linhasGrupo, agregacoes),
      filho: construirArvore(linhasGrupo, nivel + 1, agrupamentos, agregacoes, pivot),
    })),
  };
  if (pivot?.total && nivel === 0) arvore.totalGeral = celulasDoPivot(linhas, pivot);
  return arvore;
}
