<script>
  export let dados = null;

  $: valor = dados?.valor ?? 0;
  $: label = dados?.label ?? '—';
  $: prefixo = dados?.prefixo ?? '';
  $: delta = dados?.delta ?? null;
  $: deltaDir = dados?.delta_dir ?? null;

  const fmt = (v) => {
    if (prefixo === 'R$') {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
    }
    if (prefixo === '%') return `${Number(v).toFixed(1)}%`;
    return new Intl.NumberFormat('pt-BR').format(v);
  };
</script>

<div class="kpi-card card">
  <span class="label">{label}</span>
  <span class="valor">{fmt(valor)}</span>
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
</style>
