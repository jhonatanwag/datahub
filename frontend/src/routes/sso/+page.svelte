<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { token } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';

  let erro = '';

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const exchange = params.get('exchange');
    if (!exchange) { erro = 'Link inválido.'; return; }

    try {
      const res = await api.ssoTrocar(exchange);
      token.set(res.token);
      goto(`/painel/${res.painel_slug}`);
    } catch {
      erro = 'Link inválido ou expirado.';
    }
  });
</script>

<svelte:head><title>Entrando... — DataHub</title></svelte:head>

<div class="wrap">
  {#if erro}
    <p class="error">{erro}</p>
  {:else}
    <p>Entrando...</p>
  {/if}
</div>

<style>
.wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  color: var(--text);
}
.error { color: var(--danger, #f85149); }
</style>
