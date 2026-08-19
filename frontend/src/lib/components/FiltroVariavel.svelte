<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '$lib/api.js';

  export let variavel;
  export let valor = {};

  const dispatch = createEventDispatcher();
  let opcoes = [];
  let aberto = false;
  let busca = '';
  let containerEl;
  let buscaInput;

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

  $: opcoesFiltradas = busca.trim()
    ? opcoes.filter(o => (o.label ?? '').toLowerCase().includes(busca.trim().toLowerCase()))
    : opcoes;

  $: valoresSelecionados = variavel.tipo === 'multiselect' && valor[variavel.slug]
    ? valor[variavel.slug].split(',')
    : [];

  $: labelBotao = variavel.tipo === 'multiselect'
    ? rotuloMulti(valoresSelecionados)
    : rotuloUnico(valor[variavel.slug]);

  function rotuloUnico(valorAtual) {
    if (!valorAtual) return 'Todos';
    const opt = opcoes.find(o => String(o.valor) === String(valorAtual));
    return opt ? opt.label : valorAtual;
  }

  function rotuloMulti(selecionados) {
    if (selecionados.length === 0) return 'Todos';
    if (selecionados.length === 1) return rotuloUnico(selecionados[0]);
    return `${selecionados.length} selecionados`;
  }

  function abrirDropdown() {
    aberto = true;
    busca = '';
    setTimeout(() => buscaInput?.focus(), 0);
  }

  function fecharDropdown() {
    aberto = false;
  }

  function toggleDropdown() {
    if (aberto) fecharDropdown();
    else abrirDropdown();
  }

  function selecionarUnico(opt) {
    emitir({ [variavel.slug]: opt ? opt.valor : '' });
    fecharDropdown();
  }

  function toggleMulti(opt) {
    const val = String(opt.valor);
    const idx = valoresSelecionados.indexOf(val);
    const novos = idx >= 0
      ? valoresSelecionados.filter((_, i) => i !== idx)
      : [...valoresSelecionados, val];
    emitir({ [variavel.slug]: novos.join(',') });
  }

  function aoClicarFora(e) {
    if (aberto && containerEl && !containerEl.contains(e.target)) {
      fecharDropdown();
    }
  }

  function aoTeclar(e) {
    if (aberto && e.key === 'Escape') fecharDropdown();
  }
</script>

<svelte:window onclick={aoClicarFora} onkeydown={aoTeclar} />

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
    <div class="filtro-dropdown" bind:this={containerEl}>
      <button type="button" class="dropdown-toggle" onclick={toggleDropdown} aria-haspopup="listbox" aria-expanded={aberto}>
        <span class="dropdown-label">{labelBotao}</span>
        <svg class="dropdown-chevron" class:rotated={aberto} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {#if aberto}
        <div class="dropdown-panel">
          <input
            type="text"
            class="dropdown-busca"
            placeholder="Pesquisar..."
            bind:value={busca}
            bind:this={buscaInput}
          />
          <div class="dropdown-lista" role="listbox">
            <button type="button" class="dropdown-opcao" class:selecionada={!valor[variavel.slug]} onclick={() => selecionarUnico(null)}>
              Todos
            </button>
            {#each opcoesFiltradas as opt}
              <button type="button" class="dropdown-opcao" class:selecionada={String(valor[variavel.slug] ?? '') === String(opt.valor)} onclick={() => selecionarUnico(opt)}>
                {opt.label}
              </button>
            {/each}
            {#if opcoesFiltradas.length === 0}
              <div class="dropdown-vazio">Nenhum resultado</div>
            {/if}
          </div>
        </div>
      {/if}
    </div>

  {:else if variavel.tipo === 'multiselect'}
    <div class="filtro-dropdown" bind:this={containerEl}>
      <button type="button" class="dropdown-toggle" onclick={toggleDropdown} aria-haspopup="listbox" aria-expanded={aberto}>
        <span class="dropdown-label">{labelBotao}</span>
        <svg class="dropdown-chevron" class:rotated={aberto} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {#if aberto}
        <div class="dropdown-panel">
          <input
            type="text"
            class="dropdown-busca"
            placeholder="Pesquisar..."
            bind:value={busca}
            bind:this={buscaInput}
          />
          <div class="dropdown-lista" role="listbox">
            {#each opcoesFiltradas as opt}
              <label class="dropdown-opcao dropdown-opcao-check">
                <input type="checkbox"
                  checked={valoresSelecionados.includes(String(opt.valor))}
                  onchange={() => toggleMulti(opt)}
                />
                {opt.label}
              </label>
            {/each}
            {#if opcoesFiltradas.length === 0}
              <div class="dropdown-vazio">Nenhum resultado</div>
            {/if}
          </div>
        </div>
      {/if}
    </div>

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

.filtro-dropdown {
  position: relative;
}
.dropdown-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 160px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
  padding: 8px 12px;
  cursor: pointer;
  transition: border-color .15s;
}
.dropdown-toggle:hover,
.dropdown-toggle[aria-expanded="true"] {
  border-color: var(--accent-blue);
}
.dropdown-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dropdown-chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--muted);
  transition: transform .15s;
}
.dropdown-chevron.rotated {
  transform: rotate(180deg);
}
.dropdown-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  min-width: 220px;
  max-width: 320px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25);
  padding: 8px;
}
.dropdown-busca {
  margin-bottom: 6px;
}
.dropdown-lista {
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.dropdown-opcao {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: none;
  border: none;
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
  text-align: left;
  padding: 6px 8px;
  border-radius: var(--radius);
  cursor: pointer;
}
.dropdown-opcao:hover {
  background: var(--surface2);
}
.dropdown-opcao.selecionada {
  background: var(--surface2);
  color: var(--accent);
  font-weight: 600;
}
.dropdown-opcao-check input[type="checkbox"] {
  width: auto;
  flex-shrink: 0;
}
.dropdown-vazio {
  color: var(--muted);
  font-size: 13px;
  padding: 6px 8px;
}

@media (max-width: 768px) {
  .filtro-item {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
    gap: 6px;
  }
  .filtro-sep { text-align: center; }
  .dropdown-toggle { width: 100%; }
  .dropdown-panel { left: 0; right: 0; max-width: none; }
}

@media (min-width: 1920px) {
  .filtro-label { font-size: 14px; }
  .filtro-item input { font-size: 15px; padding: 8px 12px; }
  .dropdown-toggle { font-size: 15px; padding: 8px 12px; }
}
</style>
