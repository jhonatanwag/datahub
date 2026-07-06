<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';
  import { usuario } from '$lib/stores/auth.js';

  export let tipo = 'bar';
  export let dados = [];

  let container;
  let chart;

  const COLORS = ['#79c0ff','#f78166','#56d364','#d2a8ff','#ffa657','#39d353'];

  function corVar(nome) {
    return getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  }

  function buildOption(tipo, dados) {
    const labels = dados.map(d => d.label);
    const values = dados.map(d => Number(d.valor));
    const corTexto = corVar('--text');
    const corMuted = corVar('--muted');
    const corBorda = corVar('--border');

    if (tipo === 'chart_doughnut') {
      return {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', right: 10, textStyle: { color: corTexto } },
        series: [{
          type: 'pie', radius: ['45%', '70%'],
          data: dados.map((d, i) => ({ value: Number(d.valor), name: d.label, itemStyle: { color: COLORS[i % COLORS.length] } })),
          label: { color: corTexto }
        }]
      };
    }

    const isHorizontal = tipo === 'chart_bar_horizontal';
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: isHorizontal
        ? { type: 'value', axisLabel: { color: corMuted }, splitLine: { lineStyle: { color: corBorda } } }
        : { type: 'category', data: labels, axisLabel: { color: corMuted } },
      yAxis: isHorizontal
        ? { type: 'category', data: labels, axisLabel: { color: corMuted } }
        : { type: 'value', axisLabel: { color: corMuted }, splitLine: { lineStyle: { color: corBorda } } },
      series: [{
        type: tipo === 'chart_line' ? 'line' : 'bar',
        data: values,
        smooth: tipo === 'chart_line',
        itemStyle: { color: '#79c0ff' },
        areaStyle: tipo === 'chart_line' ? { color: 'rgba(121,192,255,.1)' } : undefined,
        barMaxWidth: 40,
      }]
    };
  }

  onMount(() => {
    chart = echarts.init(container, null, { renderer: 'svg' });
    if (dados.length) chart.setOption(buildOption(tipo, dados));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(container);
    return () => ro.disconnect();
  });

  $: if (chart && dados.length) {
    $usuario?.tema; // dependência reativa: recria a option quando o tema muda
    chart.setOption(buildOption(tipo, dados), true);
  }

  onDestroy(() => chart?.dispose());
</script>

<div bind:this={container} style="width:100%;height:260px;"></div>
