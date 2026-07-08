<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';
  import { usuario } from '$lib/stores/auth.js';

  export let tipo = 'bar';
  export let dados = [];
  export let fonteTamanho = 12;
  export let truncarLabel = false;
  export let truncarTamanho = 15;
  export let mostrarValor = false;
  export let valorLabel = null;

  let container;
  let chart;

  const COLORS = ['#79c0ff','#f78166','#56d364','#d2a8ff','#ffa657','#39d353'];

  function corVar(nome) {
    return getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  }

  function truncar(texto) {
    const s = String(texto ?? '');
    if (!truncarLabel || s.length <= truncarTamanho) return s;
    return s.slice(0, truncarTamanho) + '…';
  }

  // Nome de exibição de uma coluna de série: a coluna 'valor' pode ter um
  // nome customizado (valorLabel); as demais sempre mostram o próprio alias SQL.
  function nomeSerie(col) {
    return col === 'valor' && valorLabel ? valorLabel : col;
  }

  // Colunas de série: todas as chaves de dados[0] exceto 'label', que tenham valor numérico
  // em pelo menos uma linha. 'valor' sempre entra primeiro (compatibilidade com queries existentes).
  function colunasSerie(dados, multiSerie) {
    if (!dados.length) return ['valor'];
    const chaves = Object.keys(dados[0]).filter(k => k !== 'label');
    const numericas = chaves.filter(k => dados.some(d => d[k] !== null && d[k] !== '' && !isNaN(Number(d[k]))));
    if (!multiSerie) return numericas.includes('valor') ? ['valor'] : numericas.slice(0, 1);
    // 'valor' primeiro, resto na ordem em que aparecem
    const resto = numericas.filter(k => k !== 'valor');
    return numericas.includes('valor') ? ['valor', ...resto] : numericas;
  }

  function buildOption(tipo, dados) {
    const labels = dados.map(d => d.label);
    const corTexto = corVar('--text');
    const corMuted = corVar('--muted');
    const corBorda = corVar('--border');

    if (tipo === 'chart_doughnut') {
      const [colValor] = colunasSerie(dados, false);
      return {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: {
          orient: 'vertical', right: 10, textStyle: { color: corTexto, fontSize: fonteTamanho },
          formatter: (nome) => truncar(nome),
        },
        series: [{
          type: 'pie', radius: ['45%', '70%'],
          data: dados.map((d, i) => ({ value: Number(d[colValor]), name: d.label, itemStyle: { color: COLORS[i % COLORS.length] } })),
          label: {
            color: corTexto, fontSize: fonteTamanho,
            formatter: (params) => mostrarValor ? `${truncar(params.name)}: ${params.value}` : truncar(params.name),
          }
        }]
      };
    }

    const isHorizontal = tipo === 'chart_bar_horizontal';
    const cols = colunasSerie(dados, tipo === 'chart_bar' || tipo === 'chart_bar_horizontal' || tipo === 'chart_line');
    const multiSerie = cols.length > 1;

    const eixoCategoria = {
      type: 'category', data: labels,
      axisLabel: { color: corMuted, fontSize: fonteTamanho, interval: 0, formatter: truncar },
    };
    const eixoValor = {
      type: 'value', axisLabel: { color: corMuted, fontSize: fonteTamanho },
      splitLine: { lineStyle: { color: corBorda } },
    };

    const series = cols.map((col, i) => ({
      type: tipo === 'chart_line' ? 'line' : 'bar',
      name: nomeSerie(col),
      data: dados.map(d => Number(d[col])),
      smooth: tipo === 'chart_line',
      itemStyle: { color: COLORS[i % COLORS.length] },
      areaStyle: tipo === 'chart_line' ? { color: COLORS[i % COLORS.length] + '1a' } : undefined,
      barMaxWidth: 40,
      label: {
        show: mostrarValor, position: isHorizontal ? 'right' : 'top',
        color: corTexto, fontSize: fonteTamanho,
      },
    }));

    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: multiSerie ? { data: cols.map(nomeSerie), top: 0, textStyle: { color: corTexto, fontSize: fonteTamanho } } : undefined,
      grid: { left: 60, right: 20, top: multiSerie ? 40 : 20, bottom: 40 },
      xAxis: isHorizontal ? eixoValor : eixoCategoria,
      yAxis: isHorizontal ? eixoCategoria : eixoValor,
      series,
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
