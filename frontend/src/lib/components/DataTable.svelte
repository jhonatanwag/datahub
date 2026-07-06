<script>
  export let colunas = [];
  export let dados   = [];
  export let titulo  = 'dados';

  const TAMANHOS_PAGINA = [10, 50, 100, 500];
  let paginaAtual   = 1;
  let tamanhoPagina = 50;

  // Queries dinâmicas não têm schema fixo — se o chamador não informar as
  // colunas, deriva a partir das chaves da primeira linha retornada.
  $: colunasEfetivas = colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : []);

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

  function escaparCSV(valor) {
    const texto = valor === null || valor === undefined ? '' : String(valor);
    if (/[;"\n]/.test(texto)) {
      return `"${texto.replace(/"/g, '""')}"`;
    }
    return texto;
  }

  function baixarCSV() {
    const cabecalho = colunasEfetivas.map(c => escaparCSV(c.label ?? c.key)).join(';');
    const linhas = dados.map(row =>
      colunasEfetivas.map(c => escaparCSV(row[c.key])).join(';')
    );
    const conteudo = '﻿' + [cabecalho, ...linhas].join('\r\n');
    const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.csv`;

    const a = document.createElement('a');
    a.href = url;
    a.download = nomeArquivo;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunasEfetivas as col}
          <th>{col.label ?? col.key}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each dadosPaginados as row}
        <tr>
          {#each colunasEfetivas as col}
            <td>
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
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="pagination">
    <button class="btn-ghost btn-sm" on:click={baixarCSV} disabled={dados.length === 0}>
      ⬇ Baixar CSV
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
.tamanho-pagina { display: flex; align-items: center; gap: 6px; }
.tamanho-pagina select { width: auto; padding: 4px 8px; }
</style>
