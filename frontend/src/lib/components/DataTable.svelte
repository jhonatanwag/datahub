<script>
  import { baixarCSV, baixarXLSX, baixarPDF } from '$lib/exportTable.js';

  export let colunas = [];
  export let dados   = [];
  export let titulo  = 'dados';
  export let impressaoHabilitada = false;
  export let impressaoUrlBase    = null;
  export let impressaoColuna     = null;
  export let metaHabilitada    = false;
  export let metaColunaValor   = null;
  export let metaColunaInicio  = null;
  export let metaColunaFim     = null;
  export let metaCorDentro     = '#3fb950';
  export let metaCorFora       = '#f85149';
  export let pdfOrientacao     = 'retrato';

  const TAMANHOS_PAGINA = [5, 10, 50, 100, 500];
  let paginaAtual   = 1;
  let tamanhoPagina = 5;

  // Queries dinâmicas não têm schema fixo — se o chamador não informar as
  // colunas, deriva a partir das chaves da primeira linha retornada.
  $: colunasOcultas = new Set([
    impressaoHabilitada ? impressaoColuna : null,
    ...(metaHabilitada ? [metaColunaInicio, metaColunaFim] : []),
  ].filter(Boolean));
  $: colunasEfetivas = (colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
  ).filter(c => !colunasOcultas.has(c.key));

  $: mostrarAcoes = impressaoHabilitada && !!impressaoUrlBase && !!impressaoColuna;

  function imprimir(row) {
    const valor = row[impressaoColuna];
    if (!valor) return;
    window.open(`${impressaoUrlBase}${valor}`, '_blank', 'noopener');
  }

  $: totalPaginas = Math.max(1, Math.ceil(dados.length / tamanhoPagina));
  $: dadosPaginados = dados.slice(
    (paginaAtual - 1) * tamanhoPagina,
    paginaAtual * tamanhoPagina
  );

  // Reseta para a página 1 sempre que os dados mudam (novo filtro aplicado)
  // ou o tamanho de página muda, pra nunca ficar numa página vazia/inválida.
  $: dados, tamanhoPagina, (paginaAtual = 1);

  const fmtValor = (v) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);

  const STATUS_COLOR = {
    concluido: 'var(--accent-green)',
    pendente:  'var(--accent-orange)',
    cancelado: 'var(--accent)',
  };

  function corMeta(row) {
    if (!metaHabilitada || !metaColunaValor || !metaColunaInicio || !metaColunaFim) return null;
    const brutoValor  = row[metaColunaValor];
    const brutoInicio = row[metaColunaInicio];
    const brutoFim    = row[metaColunaFim];
    if (brutoValor == null || brutoInicio == null || brutoFim == null) return null;
    const valor  = Number(brutoValor);
    const inicio = Number(brutoInicio);
    const fim    = Number(brutoFim);
    if (Number.isNaN(valor) || Number.isNaN(inicio) || Number.isNaN(fim)) return null;
    return (valor >= inicio && valor <= fim) ? metaCorDentro : metaCorFora;
  }

  function estiloMeta(row, col) {
    if (col.key !== metaColunaValor) return '';
    const cor = corMeta(row);
    return cor ? `color:${cor}` : '';
  }

  let gerandoPDF = false;

  async function exportarPDF() {
    gerandoPDF = true;
    try {
      await baixarPDF(colunasEfetivas, dados, titulo, pdfOrientacao);
    } finally {
      gerandoPDF = false;
    }
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunasEfetivas as col}
          <th>{col.label ?? col.key}</th>
        {/each}
        {#if mostrarAcoes}<th>Ações</th>{/if}
      </tr>
    </thead>
    <tbody>
      {#each dadosPaginados as row}
        <tr>
          {#each colunasEfetivas as col}
            <td style={estiloMeta(row, col)}>
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </td>
          {/each}
          {#if mostrarAcoes}
            <td>
              {#if row[impressaoColuna]}
                <button class="btn-ghost btn-sm" on:click={() => imprimir(row)} title="Imprimir">🖨</button>
              {/if}
            </td>
          {/if}
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="cards-mobile">
    {#each dadosPaginados as row}
      <div class="card-linha" class:com-acao={mostrarAcoes && row[impressaoColuna]}>
        {#if mostrarAcoes && row[impressaoColuna]}
          <button class="btn-ghost btn-sm card-acao" on:click={() => imprimir(row)} title="Imprimir">🖨</button>
        {/if}
        {#each colunasEfetivas as col}
          <div class="card-campo">
            <span class="card-rotulo">{col.label ?? col.key}</span>
            <span
              class="card-valor"
              style={estiloMeta(row, col)}
            >
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </span>
          </div>
        {/each}
      </div>
    {/each}
  </div>

  <div class="pagination">
    <button class="btn-export btn-export-csv btn-sm" on:click={() => baixarCSV(colunasEfetivas, dados, titulo)} disabled={dados.length === 0}>
      ⬇ CSV
    </button>
    <button class="btn-export btn-export-xlsx btn-sm" on:click={() => baixarXLSX(colunasEfetivas, dados, titulo)} disabled={dados.length === 0}>
      ⬇ Excel
    </button>
    <button class="btn-export btn-export-pdf btn-sm" on:click={exportarPDF} disabled={dados.length === 0 || gerandoPDF}>
      {gerandoPDF ? 'Gerando…' : '⬇ PDF'}
    </button>
    <span>{dados.length} registros</span>
    <label class="tamanho-pagina">
      Itens por página:
      <select bind:value={tamanhoPagina}>
        {#each TAMANHOS_PAGINA as tam}
          <option value={tam}>{tam}</option>
        {/each}
      </select>
    </label>
    <div class="btns">
      <button class="btn-ghost" on:click={() => paginaAtual -= 1} disabled={paginaAtual <= 1}>← Anterior</button>
      <span>Pág {paginaAtual} / {totalPaginas}</span>
      <button class="btn-ghost" on:click={() => paginaAtual += 1} disabled={paginaAtual >= totalPaginas}>Próxima →</button>
    </div>
  </div>
</div>

<style>
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
tr:hover td { background: var(--surface2); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0 0;
  color: var(--muted);
  font-size: 13px;
  gap: 12px;
  flex-wrap: wrap;
}
.btns { display: flex; gap: 8px; align-items: center; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.btn-export { color: #0d1117; font-weight: 600; border: none; }
.btn-export-csv { background: var(--accent); }
.btn-export-xlsx { background: var(--accent-blue); color: #fff; }
.btn-export-pdf { background: var(--danger, #f85149); color: #fff; }
.tamanho-pagina { display: flex; align-items: center; gap: 6px; }
.tamanho-pagina select { width: auto; padding: 4px 8px; }

.cards-mobile { display: none; }

@media (max-width: 768px) {
  table { display: none; }
  .cards-mobile { display: flex; flex-direction: column; gap: 10px; }
  .card-linha {
    position: relative;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .card-acao { position: absolute; top: 8px; right: 8px; }
  .card-linha.com-acao { padding-right: 48px; }
  .card-campo { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; align-items: baseline; }
  .card-rotulo { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; }
  .card-valor { text-align: right; min-width: 0; overflow-wrap: anywhere; }
}
</style>
