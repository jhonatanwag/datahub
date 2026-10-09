<script>
  import { createEventDispatcher } from 'svelte';
  import { assetUrl } from '$lib/api.js';
  import KPICard      from '$lib/components/KPICard.svelte';
  import ChartPanel   from '$lib/components/ChartPanel.svelte';
  import DataTable    from '$lib/components/DataTable.svelte';
  import DynamicTable from '$lib/components/DynamicTable.svelte';
  import MapPanel     from '$lib/components/MapPanel.svelte';
  import CardPerfil   from '$lib/components/CardPerfil.svelte';

  export let painel;
  export let indicadores = [];
  export let slug = '';
  export let filtrosAtivos = {};
  export let filtrosQuery = '';
  export let urlImpressaoBase = null;

  const dispatch = createEventDispatcher();

  function valoresClicados(ind) {
    const s = ind.filtro_clique_variavel_slug;
    if (!s) return [];
    const val = filtrosAtivos[s];
    if (!val) return [];
    return ind.filtro_clique_variavel_tipo === 'multiselect' ? String(val).split(',') : [String(val)];
  }
</script>

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
      {#if ind.erro || ind.query_tipo !== 'kpi'}
        <div class="card-titulo">{ind.titulo || ind.query_slug}</div>
      {/if}

      {#if ind.erro}
        <p class="error" style="font-size:12px; padding:8px">{ind.erro}</p>

      {:else if ind.query_tipo === 'kpi'}
        <KPICard
          dados={ind.dados?.[0]}
          corFonte={ind.kpi_cor_fonte}
          corFundo={ind.kpi_cor_fundo}
          imagemUrl={ind.kpi_imagem_habilitada ? assetUrl(`/api/queries/${ind.query_id}/kpi-imagem`) : null}
          imagemPosicao={ind.kpi_imagem_posicao}
          valorPrimeiro={ind.kpi_valor_primeiro}
          descricao={ind.descricao}
          titulo={ind.titulo || ind.query_slug}
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
          rotuloEixo={ind.chart_rotulo_eixo}
          rotuloValor={ind.chart_rotulo_valor}
          filtroColuna={ind.chart_filtro_coluna}
          valoresSelecionados={valoresClicados(ind)}
          on:filtroClique={(e) => dispatch('filtroClique', { ind, valor: e.detail.valor })}
        />

      {:else if ind.query_tipo === 'table'}
        <DataTable
          dados={ind.dados}
          titulo={ind.titulo || ind.query_slug}
          painelSlug={slug}
          indicadorId={ind.id}
          filtrosQuery={filtrosQuery}
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
        />

      {:else if ind.query_tipo === 'table_dynamic'}
        <DynamicTable
          dados={ind.dados}
          titulo={ind.titulo || ind.query_slug}
          painelSlug={slug}
          indicadorId={ind.id}
          filtrosQuery={filtrosQuery}
          agrupamentos={ind.agrupamentos ?? []}
          agregacoes={ind.agregacoes ?? []}
          pivot={ind.pivot ?? null}
          faixasCor={ind.faixas_cor ?? null}
          subquery={ind.subquery}
        />

      {:else if ind.query_tipo === 'card'}
        <CardPerfil dados={ind.dados?.[0] ?? null} vazio="Use os filtros para pesquisar e consultar as informações." />

      {:else if ind.query_tipo === 'map'}
        <MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} altura={300 * Math.max(1, Number(ind.row_span) || 1)} />

      {:else}
        <p class="muted" style="font-size:12px; padding:8px">Tipo "{ind.query_tipo}" não suportado</p>
      {/if}
    </div>
  {/each}
</div>

<style>
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
  letter-spacing: .06em;
  border-bottom: 1px solid var(--border);
}

.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }

/* ── Tablet (≤1024px) ───────────────────────────────────── */
@media (max-width: 1024px) {
  .painel-grid  { grid-template-columns: repeat(2, 1fr) !important; }
  .grid-item    { grid-column: auto !important; grid-row: auto !important; }
}

/* ── Mobile (≤768px) ────────────────────────────────────── */
@media (max-width: 768px) {
  .painel-grid  { grid-template-columns: 1fr !important; gap: 10px; }
  .grid-item    { grid-column: 1 / -1 !important; grid-row: auto !important; }
  .card-titulo  { font-size: 11px; padding: 10px 12px 6px; }
}

/* ── TV (≥1920px) ───────────────────────────────────────── */
@media (min-width: 1920px) {
  .painel-grid { gap: 24px; }
  .card-titulo { font-size: 14px; padding: 16px 20px 10px; }
}
</style>
