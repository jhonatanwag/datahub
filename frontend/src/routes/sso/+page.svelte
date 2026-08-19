<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { token, usuario, empresaAtiva, menuPaineis } from '$lib/stores/auth.js';
  import { api, assetUrl } from '$lib/api.js';

  let erro = '';

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const exchange = params.get('exchange');
    if (!exchange) { erro = 'Link inválido.'; return; }

    try {
      const res = await api.ssoTrocar(exchange);
      token.set(res.token);

      const me = await api.me();
      usuario.set(me);
      empresaAtiva.set({
        id: me.empresa_id, slug: me.company_slug,
        nome: me.company_name,
        logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
        url_impressao_base: me.url_impressao_base ?? null
      });
      menuPaineis.set(await api.meuMenu());

      goto('/');
    } catch {
      erro = 'Link inválido ou expirado.';
    }
  });
</script>

<svelte:head><title>Entrando... — GPA Analytics</title></svelte:head>

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
