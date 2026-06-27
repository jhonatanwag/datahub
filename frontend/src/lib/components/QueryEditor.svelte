<script>
  export let sql   = '';
  export let tipo  = 'kpi';
  export let onTestar;

  let linhas     = 0;
  let colunas    = [];
  let amostra    = [];
  let erro       = null;
  let testando   = false;

  const contratos = {
    kpi:                  ['valor', 'label'],
    chart_line:           ['label', 'valor'],
    chart_bar:            ['label', 'valor'],
    chart_bar_horizontal: ['label', 'valor'],
    chart_doughnut:       ['label', 'valor'],
    table:                [],
    rag_context:          [],
    map:                  ['lat', 'lng', 'valor', 'label'],
  };

  $: colunasEsperadas  = contratos[tipo] || [];
  $: colunasFaltando   = colunasEsperadas.filter(c => !colunas.includes(c));
  $: contratoOk        = colunas.length > 0 && colunasFaltando.length === 0;

  async function testar() {
    testando = true;
    erro = null;
    try {
      const res = await onTestar(sql);
      if (res.ok) {
        linhas  = res.linhas;
        colunas = res.colunas;
        amostra = res.amostra;
      } else {
        erro = res.erro;
        linhas = 0; colunas = []; amostra = [];
      }
    } catch (e) {
      erro = e.message || 'Erro ao testar query';
      linhas = 0; colunas = []; amostra = [];
    } finally {
      testando = false;
    }
  }
</script>

<div class="editor">
  <textarea
    bind:value={sql}
    rows="8"
    placeholder="SELECT coluna AS label, valor FROM tabela WHERE ..."
    style="font-family: var(--font-display); font-size: 13px;"
  ></textarea>

  <button class="btn-ghost" on:click={testar} disabled={testando || !sql.trim()}>
    {testando ? 'Testando...' : 'Testar Query'}
  </button>

  {#if erro}
    <p class="error">{erro}</p>
  {/if}

  {#if colunas.length > 0}
    <div class="result-info">
      <span>{linhas} linha(s) retornada(s)</span>
      <span>Colunas: {colunas.join(', ')}</span>
      {#if colunasFaltando.length > 0}
        <p class="error">⚠ Colunas obrigatórias faltando para tipo "{tipo}": {colunasFaltando.join(', ')}</p>
      {:else if colunasEsperadas.length > 0}
        <p style="color: var(--accent-green)">✓ Contrato OK</p>
      {/if}
    </div>

    {#if amostra.length > 0}
      <div class="preview">
        <table>
          <thead><tr>{#each colunas as c}<th>{c}</th>{/each}</tr></thead>
          <tbody>
            {#each amostra as row}
              <tr>{#each colunas as c}<td>{row[c] ?? '—'}</td>{/each}</tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</div>

<style>
.editor { display: flex; flex-direction: column; gap: 10px; }
.result-info { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--muted); }
.preview { overflow-x: auto; }
.preview table { border-collapse: collapse; font-size: 12px; }
.preview th, .preview td { padding: 6px 10px; border: 1px solid var(--border); }
.preview th { background: var(--surface2); color: var(--muted); }
</style>
