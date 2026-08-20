<script>
  import { page } from '$app/stores';
  import { afterNavigate } from '$app/navigation';
  import { api, assetUrl } from '$lib/api.js';
  import KPICard        from '$lib/components/KPICard.svelte';
  import ChartPanel     from '$lib/components/ChartPanel.svelte';
  import DataTable      from '$lib/components/DataTable.svelte';
  import DynamicTable   from '$lib/components/DynamicTable.svelte';
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
  let opcoesPorVariavel = {}; // { [slug]: [{valor, label}, ...] } — pra exibir o label no chip de resumo
  let urlImpressaoBase = null;

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

    if (v.tipo === 'select' || v.tipo === 'multiselect') {
      const opcoes = opcoesPorVariavel[v.slug] || [];
      const labels = String(val).split(',').map(id => {
        const opt = opcoes.find(o => String(o.valor) === id);
        return opt ? opt.label : id;
      });
      return [{ nome: v.nome, valor: labels.join(', ') }];
    }

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

  // Valores padrão dos filtros (mesmos que a tela usa na primeira abertura)
  function valoresIniciais() {
    const v = {};
    variaveis.forEach(variavel => {
      if (variavel.tipo === 'date_range') {
        v[variavel.slug + '_inicio'] = resolverToken(variavel.valor_padrao_inicio || '');
        v[variavel.slug + '_fim']    = resolverToken(variavel.valor_padrao_fim    || '');
      } else {
        v[variavel.slug] = resolverToken(variavel.valor_padrao || '');
      }
    });
    return v;
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

      filtrosAtivos = valoresIniciais();

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
    filtrosAtivos = valoresIniciais();
    filtrosAbertos = false;
    await carregarDados();
  }

  function onFiltroMudou(event) {
    filtrosAtivos = { ...filtrosAtivos, ...event.detail };
  }

  function valoresClicados(ind) {
    const slug = ind.filtro_clique_variavel_slug;
    if (!slug) return [];
    const val = filtrosAtivos[slug];
    if (!val) return [];
    return ind.filtro_clique_variavel_tipo === 'multiselect' ? String(val).split(',') : [String(val)];
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
              <KPICard
                dados={ind.dados?.[0]}
                corFonte={ind.kpi_cor_fonte}
                corFundo={ind.kpi_cor_fundo}
                imagemUrl={ind.kpi_imagem_habilitada ? assetUrl(`/api/queries/${ind.query_id}/kpi-imagem`) : null}
                imagemPosicao={ind.kpi_imagem_posicao}
              />

            {:else if ind.query_tipo?.startsWith('chart_')}
              <ChartPanel
                tipo={ind.query_tipo}
                dados={ind.dados}
                fonteTamanho={ind.chart_fonte_tamanho}
                truncarLabel={ind.chart_truncar_label}
                truncarTamanho={ind.chart_truncar_tamanho}
                mostrarValor={ind.chart_mostrar_valor}
                valorLabel={ind.chart_valor_label}
                filtroColuna={ind.chart_filtro_coluna}
                valoresSelecionados={valoresClicados(ind)}
                on:filtroClique={(e) => onFiltroClique(ind, e.detail.valor)}
              />

            {:else if ind.query_tipo === 'table'}
              <DataTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                impressaoHabilitada={ind.impressao_habilitada}
                impressaoUrlBase={
                  ind.impressao_habilitada && urlImpressaoBase && ind.impressao_caminho
                    ? `${urlImpressaoBase}${ind.impressao_caminho}`
                    : null
                }
                impressaoColuna={ind.impressao_coluna}
                metaHabilitada={ind.meta_habilitada}
                metaColunaValor={ind.meta_coluna_valor}
                metaColunaInicio={ind.meta_coluna_inicio}
                metaColunaFim={ind.meta_coluna_fim}
                metaCorDentro={ind.meta_cor_dentro}
                metaCorFora={ind.meta_cor_fora}
                pdfOrientacao={ind.pdf_orientacao}
              />

            {:else if ind.query_tipo === 'table_dynamic'}
              <DynamicTable
                dados={ind.dados}
                titulo={ind.titulo || ind.query_slug}
                agrupamentos={ind.agrupamentos ?? []}
                agregacoes={ind.agregacoes ?? []}
                subquery={ind.subquery}
                pdfOrientacao={ind.pdf_orientacao}
              />

            {:else if ind.query_tipo === 'map'}
              <MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} />

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
  .filtros-acoes { margin-left: 0; width: 100%; }
  .btn-limpar,
  .btn-aplicar  { flex: 1; justify-content: center; }

  .painel-grid  { grid-template-columns: 1fr !important; gap: 10px; }
  .grid-item    { grid-column: 1 / -1 !important; grid-row: auto !important; }
  .card-titulo  { font-size: 11px; padding: 10px 12px 6px; }
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
