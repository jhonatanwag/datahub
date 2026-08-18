<script>
  export let no;              // { folha: true, linhas } | { folha: false, grupos: [{valor, agregados, filho}] }
  export let colunasDetalhe;  // [{key, label}]
  export let agregacoes = []; // [{coluna, funcao, label}] — used only to pad leaf-row cell count
  export let mostrarAcoes;
  export let onAcionar;
  export let nivel = 0;
</script>

{#if no.folha}
  {#each no.linhas as row}
    <tr>
      {#each colunasDetalhe as col, i}
        <td style={i === 0 ? `padding-left:${16 + nivel * 16}px` : ''}>{row[col.key] ?? '—'}</td>
      {/each}
      {#each agregacoes as ag}<td></td>{/each}
      {#if mostrarAcoes}
        <td><button class="btn-ghost btn-sm" on:click={() => onAcionar(row)}>Ações</button></td>
      {/if}
    </tr>
  {/each}
{:else}
  {#each no.grupos as grupo}
    <tr class="linha-grupo">
      <td style="padding-left:{nivel * 16}px" colspan={Math.max(1, colunasDetalhe.length)}>
        {grupo.valor}
      </td>
      {#each grupo.agregados as ag}
        <td class="agregado">{ag.label ?? ag.coluna}: {ag.valor}</td>
      {/each}
      {#if mostrarAcoes}<td></td>{/if}
    </tr>
    <svelte:self
      no={grupo.filho}
      {colunasDetalhe}
      {agregacoes}
      {mostrarAcoes}
      {onAcionar}
      nivel={nivel + 1}
    />
  {/each}
{/if}

<style>
.linha-grupo { background: var(--surface2); font-weight: 600; }
.agregado { text-align: right; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
