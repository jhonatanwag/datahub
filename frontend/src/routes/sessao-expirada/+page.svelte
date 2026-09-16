<script>
  import { page } from '$app/stores';

  $: veioDoApp = $page.url.searchParams.get('origem') === 'app';
</script>

<svelte:head><title>Sessão expirada — GPA Analytics</title></svelte:head>

<div class="wrap">
  <div class="box card">
    <h1>Sessão expirada</h1>
    {#if veioDoApp}
      <p>Sua sessão expirou. Volte ao menu do aplicativo e conecte-se novamente.</p>
    {:else}
      <p>Sua sessão expirou. Faça login novamente para continuar.</p>
      <a class="btn-primary" href="/login">Ir para o login</a>
    {/if}
  </div>
</div>

<style>
.wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.box {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  text-align: center;
}
h1  { font-family: var(--font-display); font-size: 22px; color: var(--accent); }
p   { color: var(--muted); }
</style>
