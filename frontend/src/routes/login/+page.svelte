<script>
  import { goto } from '$app/navigation';
  import { token, usuario } from '$lib/stores/company.js';
  import { api } from '$lib/api.js';

  let email        = '';
  let senha        = '';
  let company_slug = 'alpha';
  let erro         = '';
  let carregando   = false;

  const empresas = [
    { slug: 'alpha', nome: 'Empresa Alpha Ltda' },
    { slug: 'beta',  nome: 'Beta Comércio S.A.' },
    { slug: 'gamma', nome: 'Gamma Tech ME' },
  ];

  async function login() {
    erro = '';
    carregando = true;
    try {
      const res = await api.login(email, senha, company_slug);
      localStorage.setItem('token', res.token);
      token.set(res.token);
      goto('/');
    } catch (e) {
      erro = 'Email, senha ou empresa inválidos.';
    } finally {
      carregando = false;
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter') login();
  }
</script>

<svelte:head><title>Login — DataHub</title></svelte:head>

<div class="login-wrap">
  <div class="login-box card">
    <h1>DataHub</h1>
    <p class="subtitle">Analytics Multiempresa</p>

    <label>Email
      <input type="email" bind:value={email} on:keydown={onKeydown} placeholder="admin@datahub.local" />
    </label>

    <label>Senha
      <input type="password" bind:value={senha} on:keydown={onKeydown} placeholder="••••••••" />
    </label>

    <label>Empresa
      <select bind:value={company_slug}>
        {#each empresas as e}
          <option value={e.slug}>{e.nome}</option>
        {/each}
      </select>
    </label>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={login} disabled={carregando}>
      {carregando ? 'Entrando...' : 'Entrar'}
    </button>
  </div>
</div>

<style>
.login-wrap {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: var(--bg);
}
.login-box { width: 100%; max-width: 380px; display: flex; flex-direction: column; gap: 16px; }
h1 { font-family: var(--font-display); font-size: 28px; color: var(--accent); }
.subtitle { color: var(--muted); margin-top: -10px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
button { margin-top: 8px; }
</style>
