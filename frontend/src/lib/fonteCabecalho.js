// Tamanho de fonte (px) dos cabeçalhos de tabela no relatório: o título só pode quebrar em espaços
// (a palavra aparece inteira), então a fonte encolhe até a MAIOR palavra caber na largura de uma coluna.
// larguraTabela = largura disponível (px); padding = soma do padding horizontal da célula (px).
const FONTE_MAX = 11;
const FONTE_MIN = 5.5;
const LARGURA_MEDIA_CHAR = 0.62; // em "em" — fonte sans em caixa alta com espaçamento entre letras

export function fonteCabecalho(rotulos, larguraTabela, padding = 16) {
  const colunas = rotulos.length;
  if (!colunas || !larguraTabela) return FONTE_MAX;
  const maiorPalavra = Math.max(
    1,
    ...rotulos.flatMap(r => String(r ?? '').split(/\s+/).map(p => p.length)),
  );
  const larguraColuna = larguraTabela / colunas - padding;
  const px = larguraColuna / (maiorPalavra * LARGURA_MEDIA_CHAR);
  return Math.max(FONTE_MIN, Math.min(FONTE_MAX, Math.floor(px * 10) / 10));
}
