<script>
  export let no;              // { folha: true, linhas } | { folha: false, grupos: [{valor, agregados, filho}] }
  export let colunasDetalhe;  // [{key, label}]
  export let agregacoes = []; // [{coluna, funcao, label}] — used only to pad leaf-row cell count
  export let mostrarAcoes;
  export let onAcionar;
  export let nivel = 0;
  export let modo = 'tabela';  // 'tabela' | 'cards' — mesmo dado, duas renderizações (padrão do DataTable.svelte)
  export let expandidos;       // Set<string> — chaves dos grupos abertos
  export let onAlternar;       // (chave) => void
  export let caminho = '';     // prefixo acumulado dos valores dos grupos ancestrais, pra montar a chave

  function chaveDoGrupo(valor) {
    return `${caminho}›${valor}`;
  }
</script>

{#if modo === 'tabela'}
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
      {@const chave = chaveDoGrupo(grupo.valor)}
      {@const aberto = expandidos.has(chave)}
      <tr class="linha-grupo" on:click={() => onAlternar(chave)}>
        <td style="padding-left:{nivel * 16}px" colspan={Math.max(1, colunasDetalhe.length)}>
          <span class="seta" class:aberta={aberto}>▶</span>
          {grupo.valor ?? '—'}
        </td>
        {#each grupo.agregados as ag}
          <td class="agregado">{ag.label ?? ag.coluna}: {ag.valor}</td>
        {/each}
        {#if mostrarAcoes}<td></td>{/if}
      </tr>
      {#if aberto}
        <svelte:self
          no={grupo.filho}
          {colunasDetalhe}
          {agregacoes}
          {mostrarAcoes}
          {onAcionar}
          nivel={nivel + 1}
          modo="tabela"
          {expandidos}
          {onAlternar}
          caminho={chave}
        />
      {/if}
    {/each}
  {/if}
{:else}
  {#if no.folha}
    {#each no.linhas as row}
      <div class="card-linha" style="margin-left:{nivel * 12}px" class:com-acao={mostrarAcoes}>
        {#if mostrarAcoes}
          <button class="btn-ghost btn-sm card-acao" on:click={() => onAcionar(row)} title="Ações">⚙</button>
        {/if}
        {#each colunasDetalhe as col}
          <div class="card-campo">
            <span class="card-rotulo">{col.label ?? col.key}</span>
            <span class="card-valor">{row[col.key] ?? '—'}</span>
          </div>
        {/each}
      </div>
    {/each}
  {:else}
    {#each no.grupos as grupo}
      {@const chave = chaveDoGrupo(grupo.valor)}
      {@const aberto = expandidos.has(chave)}
      <div class="card-grupo" style="margin-left:{nivel * 12}px" on:click={() => onAlternar(chave)}>
        <span class="seta" class:aberta={aberto}>▶</span>
        <span class="card-grupo-valor">{grupo.valor ?? '—'}</span>
        {#if grupo.agregados.length}
          <div class="card-grupo-agregados">
            {#each grupo.agregados as ag}
              <span class="card-agregado-pill">{ag.label ?? ag.coluna}: {ag.valor}</span>
            {/each}
          </div>
        {/if}
      </div>
      {#if aberto}
        <svelte:self
          no={grupo.filho}
          {colunasDetalhe}
          {agregacoes}
          {mostrarAcoes}
          {onAcionar}
          nivel={nivel + 1}
          modo="cards"
          {expandidos}
          {onAlternar}
          caminho={chave}
        />
      {/if}
    {/each}
  {/if}
{/if}

<style>
.linha-grupo { background: var(--surface2); font-weight: 600; cursor: pointer; user-select: none; }
.linha-grupo:hover { background: var(--surface); }
.agregado { text-align: right; }
.btn-sm { font-size: 12px; padding: 4px 10px; }

.seta {
  display: inline-block;
  font-size: 9px;
  margin-right: 6px;
  color: var(--muted);
  transition: transform .15s;
}
.seta.aberta { transform: rotate(90deg); }

.card-grupo {
  background: var(--surface2);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}
.card-grupo-valor { font-weight: 600; font-size: 13px; }
.card-grupo-agregados { display: flex; flex-wrap: wrap; gap: 6px; margin-left: auto; }
.card-agregado-pill {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
}

.card-linha {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.card-acao { position: absolute; top: 8px; right: 8px; }
.card-linha.com-acao { padding-right: 48px; }
.card-campo { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; align-items: baseline; }
.card-rotulo { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; }
.card-valor { text-align: right; min-width: 0; overflow-wrap: anywhere; }
</style>
