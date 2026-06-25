<script>
  import { createEventDispatcher } from 'svelte';

  export let colunas = [];
  export let dados   = [];
  export let total   = 0;
  export let page    = 1;

  const dispatch = createEventDispatcher();
  $: pages = Math.ceil(total / (dados.length || 20)) || 1;

  const fmtValor = (v) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);

  const STATUS_COLOR = {
    concluido: 'var(--accent-green)',
    pendente:  'var(--accent-orange)',
    cancelado: 'var(--accent)',
  };
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunas as col}
          <th>{col.label ?? col.key}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each dados as row}
        <tr>
          {#each colunas as col}
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
    <span>{total} registros</span>
    <div class="btns">
      <button class="btn-ghost" on:click={() => dispatch('page', page - 1)} disabled={page <= 1}>← Anterior</button>
      <span>Pág {page} / {pages}</span>
      <button class="btn-ghost" on:click={() => dispatch('page', page + 1)} disabled={page >= pages}>Próxima →</button>
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
.pagination { display: flex; justify-content: space-between; align-items: center; padding: 12px 0 0; color: var(--muted); font-size: 13px; }
.btns { display: flex; gap: 8px; align-items: center; }
</style>
