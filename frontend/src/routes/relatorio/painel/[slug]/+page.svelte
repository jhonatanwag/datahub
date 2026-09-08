<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import { api, assetUrl } from '$lib/api.js';
  import { resumoFiltros } from '$lib/resumoFiltros.js';
  import RelatorioCabecalho from '$lib/relatorio/RelatorioCabecalho.svelte';
  import RelatorioRodape from '$lib/relatorio/RelatorioRodape.svelte';
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

  function filtrosDaURL() {
    const f = {};
    for (const [k, v] of params.entries()) {
      if (k === 'indicador') continue;
      f[k] = v;
    }
    return f;
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
  });

  onDestroy(() => {
    document.documentElement.classList.remove('relatorio-tema');
  });

  $: tituloRelatorio = indicadorUnico
    ? (indicadorUnico.titulo || indicadorUnico.query_slug)
    : (painel?.nome ?? 'Relatório');
  $: subtituloRelatorio = idIndicador ? 'RELAÇÃO DE DADOS' : 'RELATÓRIO DE INDICADORES';
  $: lista = indicadorUnico ? [indicadorUnico] : indicadores;
</script>

<svelte:head><title>{tituloRelatorio} — Relatório</title></svelte:head>

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
    <p style="color:#C62828">{erro}</p>
  {:else}
    <!-- placeholder — Task 5 substitui pelo grid real -->
    <ul>
      {#each lista as ind}
        <li>{ind.titulo || ind.query_slug} — {ind.query_tipo}{#if ind.erro} (erro: {ind.erro}){/if}</li>
      {/each}
    </ul>
  {/if}
</div>

<RelatorioRodape />
