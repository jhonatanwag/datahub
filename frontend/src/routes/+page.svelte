<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import KPICard    from '$lib/components/KPICard.svelte';
  import ChartPanel from '$lib/components/ChartPanel.svelte';
  import DataTable  from '$lib/components/DataTable.svelte';

  let layout  = [];
  let dados   = {};
  let loading = true;
  let erro    = null;

  const COLUNAS_PEDIDOS = [
    { key: 'id',           label: 'ID' },
    { key: 'cliente_nome', label: 'Cliente' },
    { key: 'produto',      label: 'Produto' },
    { key: 'valor',        label: 'Valor' },
    { key: 'status',       label: 'Status' },
    { key: 'canal',        label: 'Canal' },
    { key: 'data',         label: 'Data' },
  ];

  onMount(async () => {
    try {
      layout = await api.layoutDashboard();

      const resultados = await Promise.allSettled(
        layout.map(w => api.executarQuery(w.query_slug))
      );

      resultados.forEach((res, i) => {
        const slug = layout[i].query_slug;
        dados[slug] = res.status === 'fulfilled' ? res.value : { erro: res.reason?.message };
      });
      dados = dados;
    } catch (e) {
      erro = e.message;
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head><title>Dashboard — DataHub</title></svelte:head>

{#if loading}
  <div class="dashboard-grid">
    {#each Array(8) as _}
      <div class="card skeleton widget--quarter" style="height:100px;"></div>
    {/each}
  </div>

{:else if erro}
  <div style="padding:24px;" class="error">Erro ao carregar dashboard: {erro}</div>

{:else}
  <div class="dashboard-grid">
    {#each layout as widget (widget.query_slug)}
      <div class="widget widget--{widget.largura} card">
        <h3 class="widget-title">{widget.titulo}</h3>

        {#if dados[widget.query_slug]?.erro}
          <p class="error" style="font-size:13px">Erro: {dados[widget.query_slug].erro}</p>

        {:else if widget.tipo === 'kpi'}
          <KPICard dados={dados[widget.query_slug]?.data?.[0]} />

        {:else if widget.tipo?.startsWith('chart_')}
          <ChartPanel tipo={widget.tipo} dados={dados[widget.query_slug]?.data ?? []} />

        {:else if widget.tipo === 'table'}
          <DataTable
            colunas={COLUNAS_PEDIDOS}
            dados={dados[widget.query_slug]?.data ?? []}
            total={dados[widget.query_slug]?.data?.length ?? 0}
            page={1}
          />
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
.widget-title { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 12px; }
@keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:.8} }
.skeleton { animation: pulse 1.5s infinite; }
</style>
