<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '$lib/api.js';

  export let variavel;
  export let valor = {};

  const dispatch = createEventDispatcher();
  let opcoes = [];

  onMount(async () => {
    if (variavel.tipo === 'select' || variavel.tipo === 'multiselect') {
      try {
        opcoes = await api.executarFonteVariavel(variavel.variavel_id || variavel.id);
      } catch (e) {
        console.error('Erro ao carregar opções:', e);
      }
    }
  });

  function emitir(params) {
    dispatch('mudou', params);
  }

  // date_range: emite sempre os dois slots juntos usando slug como prefixo
  function emitirRange(slot, val) {
    const kI = variavel.slug + '_inicio';
    const kF = variavel.slug + '_fim';
    emitir({
      [kI]: slot === 'inicio' ? val : (valor[kI] || ''),
      [kF]: slot === 'fim'   ? val : (valor[kF] || ''),
    });
  }
</script>

<div class="filtro-item">
  <label class="filtro-label">{variavel.nome}</label>

  {#if variavel.tipo === 'date_range'}
    <input type="date"
      value={valor[variavel.slug + '_inicio'] || ''}
      onchange={e => emitirRange('inicio', e.target.value)}
    />
    <span class="filtro-sep">até</span>
    <input type="date"
      value={valor[variavel.slug + '_fim'] || ''}
      onchange={e => emitirRange('fim', e.target.value)}
    />

  {:else if variavel.tipo === 'date'}
    <input type="date"
      value={valor[variavel.slug] || valor[variavel.param_names?.[0]] || ''}
      onchange={e => emitir({ [variavel.slug]: e.target.value })}
    />

  {:else if variavel.tipo === 'select'}
    <select onchange={e => emitir({ [variavel.slug]: e.target.value })}>
      <option value="">Todos</option>
      {#each opcoes as opt}
        <option value={opt.valor}>{opt.label}</option>
      {/each}
    </select>

  {:else if variavel.tipo === 'multiselect'}
    <select multiple onchange={e => {
      const vals = [...e.target.selectedOptions].map(o => o.value);
      emitir({ [variavel.slug]: vals.join(',') });
    }}>
      {#each opcoes as opt}
        <option value={opt.valor}>{opt.label}</option>
      {/each}
    </select>

  {:else if variavel.tipo === 'text'}
    <input type="text"
      placeholder="Buscar..."
      value={valor[variavel.slug] || valor[variavel.param_names?.[0]] || ''}
      oninput={e => emitir({ [variavel.slug]: e.target.value })}
    />

  {:else if variavel.tipo === 'number'}
    <input type="number"
      value={valor[variavel.slug] || valor[variavel.param_names?.[0]] || ''}
      oninput={e => emitir({ [variavel.slug]: e.target.value })}
    />
  {/if}
</div>

<style>
.filtro-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filtro-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.filtro-sep {
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 768px) {
  .filtro-item {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
    gap: 6px;
  }
  .filtro-sep { text-align: center; }
}

@media (min-width: 1920px) {
  .filtro-label { font-size: 14px; }
  .filtro-item input,
  .filtro-item select { font-size: 15px; padding: 8px 12px; }
}
</style>
