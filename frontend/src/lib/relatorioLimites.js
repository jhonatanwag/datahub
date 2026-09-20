// Teto de linhas que o relatório (PDF) renderiza por tabela. No modo relatório
// tudo é montado no DOM de uma vez (sem paginação) e o Chrome do pdf-renderer
// imprime esse DOM inteiro — dezenas de milhares de linhas viram milhões de nós
// e estouram a memória do container. Acima do limite o relatório degrada com
// aviso em vez de tentar renderizar tudo.
export const LIMITE_LINHAS_RELATORIO = 2000;

export function excedeLimiteRelatorio(total, limite = LIMITE_LINHAS_RELATORIO) {
  return total > limite;
}

const fmt = (n) => new Intl.NumberFormat('pt-BR').format(n);

// modo 'truncar'         -> tabela simples: só as primeiras `limite` linhas.
// modo 'omitir-detalhe'  -> tabela agrupada: grupos e totais completos, sem as linhas de detalhe.
export function textoAvisoLimite(total, modo, limite = LIMITE_LINHAS_RELATORIO) {
  if (modo === 'omitir-detalhe') {
    return `Detalhe omitido: a consulta tem ${fmt(total)} linhas (limite do relatório: ${fmt(limite)}). ` +
           `Os grupos e totais acima estão completos; refine os filtros para listar o detalhe.`;
  }
  return `Exibindo as primeiras ${fmt(limite)} de ${fmt(total)} linhas. ` +
         `Refine os filtros (período, ficha, propriedade…) para ver o restante.`;
}

// Colunas do pivô que cabem numa página A4. Cada coluna nova estreita as outras, o texto quebra em
// mais linhas e a altura/memória da impressão do Chrome explode (medido: 63 colunas -> page.pdf() de
// 280 s que falha; 18 colunas -> 7 s). Acima disso o relatório recusa desenhar a tabela e avisa.
export const LIMITE_COLUNAS_PIVOT_RELATORIO = 24;

export function excedeColunasPivotRelatorio(colunas, limite = LIMITE_COLUNAS_PIVOT_RELATORIO) {
  return colunas > limite;
}

export function textoAvisoColunasPivot(colunas, limite = LIMITE_COLUNAS_PIVOT_RELATORIO) {
  return `Tabela não exibida: o período selecionado gera ${fmt(colunas)} colunas e o relatório comporta no máximo ` +
         `${fmt(limite)}. Reduza o período (ou use as colunas em outro nível) e gere o PDF novamente.`;
}
