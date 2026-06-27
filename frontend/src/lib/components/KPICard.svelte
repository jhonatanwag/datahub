<script>
  export let dados    = null;
  export let corFonte = null;
  export let corFundo = null;

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

<div class="kpi-card card" style={estiloCard}>
  <span class="label" style={estiloLabel}>{label}</span>
  <span class="valor" style={estiloValor}>{fmt(valor)}</span>
  {#if delta !== null}
    <span class="delta" class:up={deltaDir === 'up'} class:down={deltaDir === 'down'}>
      {deltaDir === 'up' ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%
    </span>
  {/if}
</div>

<style>
.kpi-card { display: flex; flex-direction: column; gap: 6px; }
.label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.valor { font-family: var(--font-display); font-size: 28px; font-weight: 500; color: var(--text); }
.delta { font-size: 12px; font-weight: 600; }
.delta.up   { color: var(--accent-green); }
.delta.down { color: var(--accent); }

@media (max-width: 768px) {
  .valor { font-size: 24px; }
}

@media (min-width: 1920px) {
  .label { font-size: 15px; }
  .valor { font-size: 42px; }
  .delta { font-size: 15px; }
}
</style>
