<script>
  import { page } from '$app/stores';
  import { afterNavigate } from '$app/navigation';
  import { api, assetUrl } from '$lib/api.js';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
  import PainelGrid     from '$lib/components/PainelGrid.svelte';
  import { valoresIniciais } from '$lib/filtrosPainel.js';
  import { resumoFiltros } from '$lib/resumoFiltros.js';
  import { abrirPdf, compartilharWhatsapp, podeCompartilhar } from '$lib/relatorioPdf.js';

  let slug        = $page.params.slug;
  let painel      = null;
  let indicadores = [];
  let variaveis   = [];
  let filtrosAtivos  = {};
  let filtrosAbertos = false;
  let carregando  = true;
  let erro        = null;
  let opcoesPorVariavel = {}; // { [slug]: [{valor, label}, ...] } — pra exibir o label no chip de resumo
  let urlImpressaoBase = null;

  // Resumo legível dos filtros: [{nome, valor}]
  $: resumoFiltrosLista = resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel);

  $: filtrosQuery = new URLSearchParams(filtrosAtivos).toString();

  let gerandoPdf = false;
  const compartilhavel = podeCompartilhar();

  async function imprimirPainel() {
    gerandoPdf = true;
    try { await abrirPdf(slug, { filtrosQuery }); }
    catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
    finally { gerandoPdf = false; }
  }

  async function enviarWhatsapp() {
    gerandoPdf = true;
    try { await compartilharWhatsapp(slug, painel.nome, { filtrosQuery }); }
    catch (e) { alert('Erro: ' + e.message); }
    finally { gerandoPdf = false; }
  }

  async function carregarPainel() {
    slug = $page.params.slug;
    painel = null;
    indicadores = [];
    variaveis = [];
    filtrosAtivos = {};
    filtrosAbertos = false;
    opcoesPorVariavel = {};
    carregando = true;
    erro = null;

    try {
      painel    = await api.buscarPainelPorSlug(slug);
      variaveis = await api.variaveisPainel(painel.id);

      filtrosAtivos = valoresIniciais(variaveis);

      // Carrega as opções (valor/label) das variáveis select/multiselect
      // pra poder mostrar o label (não o id cru) no chip de resumo.
      const selects = variaveis.filter(v => v.tipo === 'select' || v.tipo === 'multiselect');
      await Promise.all(selects.map(async v => {
        try {
          opcoesPorVariavel[v.slug] = await api.executarFonteVariavel(v.variavel_id || v.id);
        } catch (e) {
          opcoesPorVariavel[v.slug] = [];
        }
      }));
      opcoesPorVariavel = { ...opcoesPorVariavel };

      await carregarDados();
    } catch (e) {
      erro = e.message;
      carregando = false;
    }
  }

  afterNavigate(() => {
    carregarPainel();
  });

  async function carregarDados() {
    carregando = true;
    erro = null;
    try {
      const resultado = await api.renderizarPainel(painel.id, filtrosAtivos);
      indicadores = resultado.indicadores;
      urlImpressaoBase = resultado.url_impressao_base;
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  async function aplicar() {
    filtrosAbertos = false;
    await carregarDados();
  }

  async function limparFiltros() {
    filtrosAtivos = valoresIniciais(variaveis);
    filtrosAbertos = false;
    await carregarDados();
  }

  function onFiltroMudou(event) {
    filtrosAtivos = { ...filtrosAtivos, ...event.detail };
  }

  function onFiltroClique(ind, valorBruto) {
    const slug = ind.filtro_clique_variavel_slug;
    if (!slug) return;
    const valor = String(valorBruto);
    if (ind.filtro_clique_variavel_tipo === 'multiselect') {
      const atuais = filtrosAtivos[slug] ? filtrosAtivos[slug].split(',').filter(Boolean) : [];
      const idx = atuais.indexOf(valor);
      const novos = idx >= 0 ? atuais.filter((_, i) => i !== idx) : [...atuais, valor];
      filtrosAtivos = { ...filtrosAtivos, [slug]: novos.join(',') };
    } else {
      filtrosAtivos = { ...filtrosAtivos, [slug]: filtrosAtivos[slug] === valor ? '' : valor };
    }
    carregarDados();
  }
</script>

<svelte:head><title>{painel?.nome ?? 'Painel'} — GPA Analytics</title></svelte:head>

<div class="painel-page">
  {#if erro && !painel}
    <p class="error">{erro}</p>

  {:else if painel}
    <div class="painel-header">
      <div class="painel-header-topo">
        <h2>{painel.nome}</h2>
        <div class="painel-header-acoes">
          <button class="btn-ghost btn-imprimir" on:click={imprimirPainel} disabled={gerandoPdf}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="6 9 6 2 18 2 18 9"/>
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
              <rect x="6" y="14" width="12" height="8"/>
            </svg>
            {gerandoPdf ? 'Gerando…' : 'Abrir PDF'}
          </button>
          {#if compartilhavel}
            <button class="btn-ghost btn-imprimir" on:click={enviarWhatsapp} disabled={gerandoPdf}>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15l-1.3 4.7 4.8-1.3A10 10 0 1 0 12 2Zm5.8 14.2c-.2.7-1.4 1.3-2 1.4-.5.1-1.2.1-1.9-.1-.4-.1-1-.3-1.7-.6-3-1.3-4.9-4.3-5.1-4.5-.1-.2-1.2-1.5-1.2-2.9 0-1.4.7-2 1-2.3.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.3 0 .5l-.4.5-.3.3c-.1.1-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.2.1.4.1.5-.1l.7-.9c.2-.2.4-.2.6-.1l1.9.9c.2.1.4.2.5.3.1.2.1.7-.1 1.3Z"/></svg>
              WhatsApp
            </button>
          {/if}
        </div>
      </div>
      {#if painel.descricao}
        <p class="descricao">{painel.descricao}</p>
      {/if}
    </div>

    {#if variaveis.length > 0}
      <!-- Barra de resumo: sempre visível -->
      <div class="filtros-toggle">
        <button
          class="btn-ghost btn-filtros"
          class:aberto={filtrosAbertos}
          on:click={() => filtrosAbertos = !filtrosAbertos}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="4" y1="6" x2="20" y2="6"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
            <line x1="11" y1="18" x2="13" y2="18"/>
          </svg>
          Filtros
          <svg class="chevron" class:rotated={filtrosAbertos} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <div class="filtros-chips">
          {#if resumoFiltrosLista.length > 0}
            {#each resumoFiltrosLista as f}
              <span class="chip">
                <span class="chip-nome">{f.nome}:</span>
                <span class="chip-val">{f.valor}</span>
              </span>
            {/each}
          {:else}
            <span class="sem-filtro">Sem filtros ativos</span>
          {/if}
        </div>
      </div>

      <!-- Painel de filtros colapsável -->
      {#if filtrosAbertos}
        <div class="filtros-bar">
          {#each variaveis as variavel}
            <FiltroVariavel
              {variavel}
              valor={filtrosAtivos}
              on:mudou={onFiltroMudou}
            />
          {/each}
          <div class="filtros-acoes">
            <button class="btn-ghost btn-limpar" on:click={limparFiltros}>Limpar filtros</button>
            <button class="btn-primary btn-aplicar" on:click={aplicar}>Aplicar</button>
          </div>
        </div>
      {/if}
    {/if}

    {#if carregando}
      <div class="loading-grid">Carregando painel...</div>
    {:else if erro}
      <p class="error">{erro}</p>
    {:else}
      <PainelGrid
        {painel}
        {indicadores}
        {slug}
        {filtrosAtivos}
        {filtrosQuery}
        {urlImpressaoBase}
        on:filtroClique={(e) => onFiltroClique(e.detail.ind, e.detail.valor)}
      />
    {/if}
  {/if}
</div>

<style>
/* ── Base ──────────────────────────────────────────────── */
.painel-page   { padding: 24px; }
.painel-header { margin-bottom: 16px; }
.painel-header h2 { font-family: var(--font-display); font-size: 20px; color: var(--text); }
.painel-header-topo { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.painel-header-acoes { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-imprimir[disabled] { opacity: .55; cursor: default; }
.btn-imprimir { display: flex; align-items: center; gap: 6px; font-size: 13px; padding: 6px 12px; border-radius: 6px; flex-shrink: 0; }
.btn-imprimir svg { width: 15px; height: 15px; }
.descricao { color: var(--muted); font-size: 13px; margin-top: 4px; }

/* ── Toggle row ─────────────────────────────────────────── */
.filtros-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.btn-filtros {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  flex-shrink: 0;
  white-space: nowrap;
}
.btn-filtros svg { width: 15px; height: 15px; }
.btn-filtros.aberto { background: var(--surface2); color: var(--text); }

.chevron { transition: transform .2s ease; }
.chevron.rotated { transform: rotate(180deg); }

/* Chips de resumo */
.filtros-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.chip {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent-blue) 12%, var(--surface2));
  border: 1px solid color-mix(in srgb, var(--accent-blue) 30%, var(--border));
  font-size: 12px;
  max-width: 100%;
}
.chip-nome { color: var(--muted); white-space: nowrap; flex-shrink: 0; }
.chip-val  { color: var(--text); font-weight: 500; white-space: normal; word-break: break-word; }

.sem-filtro { font-size: 12px; color: var(--muted); font-style: italic; }

/* ── Painel de filtros (colapsável) ─────────────────────── */
.filtros-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 20px;
}

.filtros-acoes { display: flex; gap: 8px; margin-left: auto; }

.loading-grid { padding: 48px; text-align: center; color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }

/* ── Tablet (≤1024px) ───────────────────────────────────── */
@media (max-width: 1024px) {
  .painel-page  { padding: 16px; }
}

/* ── Mobile (≤768px) ────────────────────────────────────── */
@media (max-width: 768px) {
  .painel-page  { padding: 12px; }

  .filtros-bar  {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 12px;
  }
  .filtros-acoes { margin-left: 0; width: 100%; }
  .btn-limpar,
  .btn-aplicar  { flex: 1; justify-content: center; }

}

/* ── TV (≥1920px) ───────────────────────────────────────── */
@media (min-width: 1920px) {
  .painel-page      { padding: 36px; }
  .painel-header h2 { font-size: 28px; }
  .filtros-bar      { padding: 16px 20px; gap: 20px; }
  .btn-filtros      { font-size: 15px; padding: 8px 16px; }
  .chip             { font-size: 14px; padding: 5px 14px; }
  .loading-grid     { font-size: 18px; }
}
</style>
