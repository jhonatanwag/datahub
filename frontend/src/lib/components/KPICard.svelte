<script>
  export let dados    = null;
  export let corFonte = null;
  export let corFundo = null;
  export let imagemUrl      = null;
  export let imagemPosicao  = 'direita'; // 'esquerda' | 'direita' — o valor do KPI fica sempre no lado oposto

  $: valor    = dados?.valor     ?? 0;
  $: label    = dados?.label     ?? '—';
  $: prefixo  = dados?.prefixo   ?? '';
  $: delta    = dados?.delta     ?? null;
  $: deltaDir = dados?.delta_dir ?? null;

  const fmt = (v) => {
    if (prefixo === 'R$') {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
    }
    if (prefixo === '%') return `${Number(v).toFixed(1)}%`;
    return new Intl.NumberFormat('pt-BR').format(v);
  };

  $: estiloCard  = corFundo ? `background:${corFundo}; border-color:${corFundo};` : '';
  $: estiloValor = corFonte ? `color:${corFonte};` : '';
  $: estiloLabel = corFonte ? `color:${corFonte}; opacity:.7;` : '';
</script>

<div class="kpi-card card" class:com-imagem={!!imagemUrl} style={estiloCard}>
  {#if imagemUrl && imagemPosicao === 'esquerda'}
    <img class="kpi-imagem" src={imagemUrl} alt="" />
  {/if}

  <div class="kpi-texto">
    <span class="label" style={estiloLabel}>{label}</span>
    <span class="valor" style={estiloValor}>{fmt(valor)}</span>
    {#if delta !== null}
      <span class="delta" class:up={deltaDir === 'up'} class:down={deltaDir === 'down'}>
        {deltaDir === 'up' ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%
      </span>
    {/if}
  </div>

  {#if imagemUrl && imagemPosicao !== 'esquerda'}
    <img class="kpi-imagem" src={imagemUrl} alt="" />
  {/if}
</div>

<style>
.kpi-card { display: flex; flex-direction: column; gap: 6px; }
.kpi-card.com-imagem { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.kpi-texto { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.kpi-imagem { width: 56px; height: 56px; object-fit: contain; border-radius: 6px; flex-shrink: 0; }
.label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.valor { font-family: var(--font-display); font-size: 28px; font-weight: 500; color: var(--text); }
.delta { font-size: 12px; font-weight: 600; }
.delta.up   { color: var(--accent-green); }
.delta.down { color: var(--accent); }

@media (max-width: 768px) {
  .valor { font-size: 24px; }
  .kpi-imagem { width: 44px; height: 44px; }
}

@media (min-width: 1920px) {
  .label { font-size: 15px; }
  .valor { font-size: 42px; }
  .delta { font-size: 15px; }
  .kpi-imagem { width: 72px; height: 72px; }
}
</style>
