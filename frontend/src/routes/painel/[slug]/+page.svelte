<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import KPICard        from '$lib/components/KPICard.svelte';
  import ChartPanel     from '$lib/components/ChartPanel.svelte';
  import DataTable      from '$lib/components/DataTable.svelte';
  import MapPanel       from '$lib/components/MapPanel.svelte';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';

  let slug        = $page.params.slug;
  let painel      = null;
  let indicadores = [];
  let variaveis   = [];
  let filtrosAtivos  = {};
  let filtrosAbertos = false;
  let carregando  = true;
  let erro        = null;

  // YYYY-MM-DD → DD/MM/YYYY
  function fmtData(val) {
    if (!val || val.length !== 10) return val ?? '';
    const [y, m, d] = val.split('-');
    return `${d}/${m}/${y}`;
  }

  // Resumo legível dos filtros: [{nome, valor}]
  $: resumoFiltros = variaveis.flatMap(v => {
    if (v.tipo === 'date_range') {
      const ini = filtrosAtivos[v.slug + '_inicio'];
      const fim = filtrosAtivos[v.slug + '_fim'];
      if (!ini && !fim) return [];
      return [{ nome: v.nome, valor: `${fmtData(ini) || '—'} até ${fmtData(fim) || '—'}` }];
    }
    const val = filtrosAtivos[v.slug];
    if (!val) return [];
    return [{ nome: v.nome, valor: String(val) }];
  });

  function resolverToken(val) {
    if (!val) return '';
    const h   = new Date();
    const ano = h.getFullYear(), mes = h.getMonth() + 1;
    const fmt = (y, m, d) => `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const ultimoDia       = new Date(ano, mes, 0).getDate();
    const mesAnt          = mes === 1 ? 12 : mes - 1;
    const anoAnt          = mes === 1 ? ano - 1 : ano;
    const ultimoDiaMesAnt = new Date(anoAnt, mesAnt, 0).getDate();
    const tokens = {
      'hoje':                fmt(ano, mes, h.getDate()),
      'ontem':               (() => { const d = new Date(h); d.setDate(d.getDate()-1); return fmt(d.getFullYear(), d.getMonth()+1, d.getDate()); })(),
      'mes_atual_inicio':    fmt(ano, mes, 1),
      'mes_atual_fim':       fmt(ano, mes, ultimoDia),
      'mes_anterior_inicio': fmt(anoAnt, mesAnt, 1),
      'mes_anterior_fim':    fmt(anoAnt, mesAnt, ultimoDiaMesAnt),
      'ano_atual_inicio':    fmt(ano, 1, 1),
      'ano_atual_fim':       fmt(ano, 12, 31),
    };
    return tokens[val] ?? val;
  }

  onMount(async () => {
    try {
      painel    = await api.buscarPainelPorSlug(slug);
      variaveis = await api.variaveisPainel(painel.id);

      variaveis.forEach(v => {
        if (v.tipo === 'date_range') {
          filtrosAtivos[v.slug + '_inicio'] = resolverToken(v.valor_padrao_inicio || '');
          filtrosAtivos[v.slug + '_fim']    = resolverToken(v.valor_padrao_fim    || '');
        } else {
          filtrosAtivos[v.slug] = resolverToken(v.valor_padrao || '');
        }
      });

      await carregarDados();
    } catch (e) {
      erro = e.message;
      carregando = false;
    }
  });

  async function carregarDados() {
    carregando = true;
    erro = null;
    try {
      const resultado = await api.renderizarPainel(painel.id, filtrosAtivos);
      indicadores = resultado.indicadores;
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

  function onFiltroMudou(event) {
    filtrosAtivos = { ...filtrosAtivos, ...event.detail };
  }
</script>

<svelte:head><title>{painel?.nome ?? 'Painel'} — DataHub</title></svelte:head>

<div class="painel-page">
  {#if erro && !painel}
    <p class="error">{erro}</p>

  {:else if painel}
    <div class="painel-header">
      <h2>{painel.nome}</h2>
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
          {#if resumoFiltros.length > 0}
            {#each resumoFiltros as f}
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
          <button class="btn-primary btn-aplicar" on:click={aplicar}>Aplicar</button>
        </div>
      {/if}
    {/if}

    {#if carregando}
      <div class="loading-grid">Carregando painel...</div>
    {:else if erro}
      <p class="error">{erro}</p>
    {:else}
      <div
        class="painel-grid"
        style="grid-template-columns: repeat({painel.colunas}, 1fr)"
      >
        {#each indicadores as ind}
          <div
            class="grid-item"
            style="
              grid-column: {ind.coluna} / span {ind.col_span};
              grid-row:    {ind.linha}  / span {ind.row_span};
            "
          >
            <div class="card-titulo">{ind.titulo || ind.query_slug}</div>

            {#if ind.erro}
              <p class="error" style="font-size:12px; padding:8px">{ind.erro}</p>

            {:else if ind.query_tipo === 'kpi'}
              <KPICard dados={ind.dados?.[0]} corFonte={ind.kpi_cor_fonte} corFundo={ind.kpi_cor_fundo} />

            {:else if ind.query_tipo?.startsWith('chart_')}
              <ChartPanel tipo={ind.query_tipo} dados={ind.dados} />

            {:else if ind.query_tipo === 'table'}
              <DataTable dados={ind.dados} titulo={ind.titulo || ind.query_slug} />

            {:else if ind.query_tipo === 'map'}
              <MapPanel pontos={ind.dados ?? []} />

            {:else}
              <p class="muted" style="font-size:12px; padding:8px">Tipo "{ind.query_tipo}" não suportado</p>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
/* ── Base ──────────────────────────────────────────────── */
.painel-page   { padding: 24px; }
.painel-header { margin-bottom: 16px; }
.painel-header h2 { font-family: var(--font-display); font-size: 20px; color: var(--text); }
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
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 20px;
  background: color-mix(in srgb, var(--accent-blue) 12%, var(--surface2));
  border: 1px solid color-mix(in srgb, var(--accent-blue) 30%, var(--border));
  font-size: 12px;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chip-nome { color: var(--muted); }
.chip-val  { color: var(--text); font-weight: 500; }

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

.btn-aplicar { margin-left: auto; }

/* ── Grid ───────────────────────────────────────────────── */
.painel-grid { display: grid; gap: 16px; }

.grid-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  min-width: 0;
}

.card-titulo {
  padding: 12px 16px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  border-bottom: 1px solid var(--border);
}

.loading-grid { padding: 48px; text-align: center; color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }

/* ── Tablet (≤1024px) ───────────────────────────────────── */
@media (max-width: 1024px) {
  .painel-page  { padding: 16px; }
  .painel-grid  { grid-template-columns: repeat(2, 1fr) !important; }
  .grid-item    { grid-column: auto !important; grid-row: auto !important; }
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
  .btn-aplicar  { margin-left: 0; width: 100%; justify-content: center; }

  .painel-grid  { grid-template-columns: 1fr !important; gap: 10px; }
  .grid-item    { grid-column: 1 / -1 !important; grid-row: auto !important; }
  .card-titulo  { font-size: 11px; padding: 10px 12px 6px; }

  .chip { max-width: 180px; }
}

/* ── TV (≥1920px) ───────────────────────────────────────── */
@media (min-width: 1920px) {
  .painel-page      { padding: 36px; }
  .painel-grid      { gap: 24px; }
  .card-titulo      { font-size: 14px; padding: 16px 20px 10px; }
  .painel-header h2 { font-size: 28px; }
  .filtros-bar      { padding: 16px 20px; gap: 20px; }
  .btn-filtros      { font-size: 15px; padding: 8px 16px; }
  .chip             { font-size: 14px; padding: 5px 14px; }
  .loading-grid     { font-size: 18px; }
}
</style>
