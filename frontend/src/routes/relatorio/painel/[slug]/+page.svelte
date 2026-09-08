<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { page } from '$app/stores';
  import { api, assetUrl } from '$lib/api.js';
  import { resumoFiltros } from '$lib/resumoFiltros.js';
  import RelatorioCabecalho from '$lib/relatorio/RelatorioCabecalho.svelte';
  import RelatorioRodape from '$lib/relatorio/RelatorioRodape.svelte';
  import KPICard      from '$lib/components/KPICard.svelte';
  import ChartPanel   from '$lib/components/ChartPanel.svelte';
  import DataTable    from '$lib/components/DataTable.svelte';
  import DynamicTable from '$lib/components/DynamicTable.svelte';
  import MapPanel     from '$lib/components/MapPanel.svelte';
  import '$lib/relatorio/tema-relatorio.css';

  const params = $page.url.searchParams;
  const slug = $page.params.slug;
  const idIndicador = params.get('indicador');

  let carregando = true;
  let erro = null;
  let painel = null;
  let indicadores = [];
  let indicadorUnico = null;
  let filtrosResumo = [];
  let empresa = { nome: '', endereco: '', cnpj: '', logo_url: null };

  let prontos = new Set();
  let pronto = false;

  function filtrosDaURL() {
    const f = {};
    for (const [k, v] of params.entries()) {
      if (k === 'indicador') continue;
      f[k] = v;
    }
    return f;
  }

  function marcarPronto(id) {
    prontos = new Set(prontos).add(id);
    verificarPronto();
  }

  async function verificarPronto() {
    if (idsAssincronos.every(id => prontos.has(id))) {
      try { await (document.fonts?.ready ?? Promise.resolve()); } catch {}
      await tick();
      pronto = true;
    }
  }

  onMount(async () => {
    document.documentElement.classList.add('relatorio-tema');
    document.documentElement.removeAttribute('data-theme');
    try {
      const me = await api.me();
      empresa = {
        nome: me.company_name ?? '',
        endereco: me.company_endereco ?? '',
        cnpj: me.company_cnpj ?? '',
        logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
      };

      painel = await api.buscarPainelPorSlug(slug);
      const variaveis = await api.variaveisPainel(painel.id);
      const filtros = filtrosDaURL();

      const opcoesPorVariavel = {};
      await Promise.all(
        variaveis
          .filter(v => v.tipo === 'select' || v.tipo === 'multiselect')
          .map(async v => {
            try { opcoesPorVariavel[v.slug] = await api.executarFonteVariavel(v.variavel_id || v.id); }
            catch { opcoesPorVariavel[v.slug] = []; }
          })
      );
      filtrosResumo = resumoFiltros(variaveis, filtros, opcoesPorVariavel);

      const resultado = await api.renderizarPainel(painel.id, filtros);
      indicadores = resultado.indicadores ?? [];
      if (idIndicador) {
        indicadorUnico = indicadores.find(i => String(i.id) === String(idIndicador)) ?? null;
      }
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }

    await tick();
    verificarPronto();                       // caso não haja chart/map nenhum
    setTimeout(() => { pronto = true; }, 12000);  // fallback: nunca trava o botão
  });

  onDestroy(() => {
    document.documentElement.classList.remove('relatorio-tema');
  });

  $: lista = indicadorUnico ? [indicadorUnico] : indicadores;
  $: idsAssincronos = lista
    .filter(i => i && (String(i.query_tipo).startsWith('chart_') || i.query_tipo === 'map') && !i.erro)
    .map(i => i.id);
  $: tituloRelatorio = indicadorUnico
    ? (indicadorUnico.titulo || indicadorUnico.query_slug)
    : (painel?.nome ?? 'Relatório');
  $: subtituloRelatorio = idIndicador ? 'RELAÇÃO DE DADOS' : 'RELATÓRIO DE INDICADORES';

  function nColunas(ind) {
    return ind?.dados?.[0] ? Object.keys(ind.dados[0]).length : 0;
  }
  $: paisagem = indicadorUnico
    ? ((indicadorUnico.query_tipo === 'table' || indicadorUnico.query_tipo === 'table_dynamic')
        && (nColunas(indicadorUnico) > 8 || indicadorUnico.pdf_orientacao === 'paisagem'))
    : (painel?.impressao_orientacao === 'paisagem');
</script>

<svelte:head>
  <title>{tituloRelatorio} — Relatório</title>
  {#if paisagem}<style>@page { size: A4 landscape; }</style>{/if}
</svelte:head>

<div class="relatorio-toolbar no-print">
  <strong>{tituloRelatorio}</strong>
  <span class="espaco"></span>
  {#if !pronto}<span class="preparando">Preparando relatório…</span>{/if}
  <button disabled={!pronto} on:click={() => window.print()}>Imprimir / Salvar PDF</button>
</div>

<RelatorioCabecalho
  titulo={tituloRelatorio}
  subtitulo={subtituloRelatorio}
  empresaNome={empresa.nome}
  empresaEndereco={empresa.endereco}
  empresaCnpj={empresa.cnpj}
  empresaLogoUrl={empresa.logo_url}
  filtros={filtrosResumo}
/>

<div class="relatorio-pagina">
  {#if carregando}
    <p>Carregando relatório…</p>
  {:else if erro}
    <p class="rel-erro">{erro}</p>
  {:else if indicadorUnico}
    <div class="rel-unico">
      <div class="card-titulo">{indicadorUnico.titulo || indicadorUnico.query_slug}</div>
      {#if indicadorUnico.query_tipo === 'table'}
        <DataTable
          dados={indicadorUnico.dados}
          titulo={tituloRelatorio}
          modoRelatorio={true}
          impressaoHabilitada={indicadorUnico.impressao_habilitada}
          impressaoColuna={indicadorUnico.impressao_coluna}
          metaHabilitada={indicadorUnico.meta_habilitada}
          metaColunaValor={indicadorUnico.meta_coluna_valor}
          metaColunaInicio={indicadorUnico.meta_coluna_inicio}
          metaColunaFim={indicadorUnico.meta_coluna_fim}
          metaCorDentro={indicadorUnico.meta_cor_dentro}
          metaCorFora={indicadorUnico.meta_cor_fora}
        />
      {:else if indicadorUnico.query_tipo === 'table_dynamic'}
        <DynamicTable
          dados={indicadorUnico.dados}
          titulo={tituloRelatorio}
          agrupamentos={indicadorUnico.agrupamentos ?? []}
          agregacoes={indicadorUnico.agregacoes ?? []}
          modoRelatorio={true}
        />
      {:else}
        <p class="rel-erro">Só tabelas têm relatório individual.</p>
      {/if}
    </div>
  {:else}
    <div class="painel-grid" style="grid-template-columns: repeat({painel.colunas}, 1fr)">
      {#each indicadores as ind}
        <div class="grid-item" style="grid-column: {ind.coluna} / span {ind.col_span}; grid-row: {ind.linha} / span {ind.row_span};">
          <div class="card-titulo">{ind.titulo || ind.query_slug}</div>

          {#if ind.erro}
            <p class="rel-erro">{ind.erro}</p>
          {:else if ind.query_tipo === 'kpi'}
            <KPICard
              dados={ind.dados?.[0]}
              corFonte={ind.kpi_cor_fonte}
              corFundo={ind.kpi_cor_fundo}
              imagemUrl={ind.kpi_imagem_habilitada ? assetUrl(`/api/queries/${ind.query_id}/kpi-imagem`) : null}
              imagemPosicao={ind.kpi_imagem_posicao}
              valorPrimeiro={ind.kpi_valor_primeiro}
              descricao={ind.descricao}
            />
          {:else if String(ind.query_tipo).startsWith('chart_')}
            <ChartPanel
              tipo={ind.query_tipo}
              dados={ind.dados}
              fonteTamanho={ind.chart_fonte_tamanho}
              truncarLabel={ind.chart_truncar_label}
              truncarTamanho={ind.chart_truncar_tamanho}
              mostrarValor={ind.chart_mostrar_valor}
              valorLabel={ind.chart_valor_label}
              on:pronto={() => marcarPronto(ind.id)}
            />
          {:else if ind.query_tipo === 'table'}
            <DataTable
              dados={ind.dados}
              titulo={ind.titulo || ind.query_slug}
              modoRelatorio={true}
              impressaoHabilitada={ind.impressao_habilitada}
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
              agrupamentos={ind.agrupamentos ?? []}
              agregacoes={ind.agregacoes ?? []}
              modoRelatorio={true}
            />
          {:else if ind.query_tipo === 'map'}
            <MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} temaForcado="claro" on:pronto={() => marcarPronto(ind.id)} />
          {:else}
            <p class="rel-erro">Tipo "{ind.query_tipo}" não suportado no relatório.</p>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<RelatorioRodape />

<style>
  .relatorio-toolbar { }
  .relatorio-toolbar .espaco { flex: 1; }
  .relatorio-toolbar .preparando { font-size: 13px; opacity: .9; }

  .painel-grid { display: grid; gap: 14px; }
  .grid-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden; min-width: 0; break-inside: avoid;
  }
  .rel-unico { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .card-titulo {
    padding: 10px 14px 6px; font-size: 11px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border);
  }
  .rel-erro { color: #C62828; font-size: 12px; padding: 8px 12px; }

  @media screen and (max-width: 820px) {
    .painel-grid { grid-template-columns: 1fr !important; }
    .grid-item { grid-column: 1 / -1 !important; grid-row: auto !important; }
  }
  @media print {
    .painel-grid { gap: 10px; }
  }
</style>
