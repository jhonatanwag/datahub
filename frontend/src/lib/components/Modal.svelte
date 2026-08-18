<script>
  export let aberto = false;
  export let onClose = () => {};

  function fecharTecla(e) {
    if (aberto && e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={fecharTecla} />

{#if aberto}
  <div class="overlay" on:click|self={onClose}>
    <div class="caixa">
      <button class="fechar" on:click={onClose} aria-label="Fechar">✕</button>
      <slot />
    </div>
  </div>
{/if}

<style>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.caixa {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  max-width: 90vw;
  max-height: 85vh;
  overflow: auto;
  position: relative;
  min-width: 320px;
}
.fechar {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 16px;
  cursor: pointer;
}
.fechar:hover { color: var(--text); }
</style>
