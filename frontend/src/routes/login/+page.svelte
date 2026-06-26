<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let email      = '';
  let senha      = '';
  let erro       = '';
  let carregando = false;

  async function login() {
    erro = '';
    carregando = true;
    try {
      const res = await api.login(email, senha);
      sessionStorage.setItem('temp_user', JSON.stringify({
        user_id: res.user_id,
        nome: res.nome,
        role: res.role,
        session_token: res.session_token,
        empresas: res.empresas
      }));
      goto('/selecionar-empresa');
    } catch {
      erro = 'E-mail ou senha inválidos.';
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

    <label>
      E-mail
      <input type="email" bind:value={email} on:keydown={onKeydown} placeholder="admin@datahub.local" />
    </label>

    <label>
      Senha
      <input type="password" bind:value={senha} on:keydown={onKeydown} placeholder="••••••••" />
    </label>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={login} disabled={carregando}>
      {carregando ? 'Entrando...' : 'Entrar'}
    </button>
  </div>
</div>

<style>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.login-box {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
h1 { font-family: var(--font-display); font-size: 28px; color: var(--accent); }
.subtitle { color: var(--muted); margin-top: -10px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
button { margin-top: 8px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
