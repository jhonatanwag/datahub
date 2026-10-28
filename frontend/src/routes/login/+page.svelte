<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import { iniciarSessaoExterna } from '$lib/sessaoExterna.js';

  const CHAVE_EMPRESA = 'loginEmpresa';

  let empresa    = '';
  let email      = '';
  let senha      = '';
  let erro       = '';
  let carregando = false;

  // Empresa vem do link (?empresa=slug) ou do último acesso com usuário do app.
  onMount(() => {
    const doLink = new URLSearchParams(window.location.search).get('empresa');
    if (doLink) { empresa = doLink; return; }
    try { empresa = localStorage.getItem(CHAVE_EMPRESA) || ''; } catch { /* sem storage */ }
  });

  async function login() {
    erro = '';
    carregando = true;
    try {
      if (empresa.trim()) await loginApp();
      else await loginDataHub();
    } finally {
      carregando = false;
    }
  }

  // Usuário e senha do app (PsoEducare): acesso aos painéis liberados, sem escolher empresa.
  async function loginApp() {
    try {
      const res = await api.loginApp(empresa.trim(), email.trim(), senha);
      try { localStorage.setItem(CHAVE_EMPRESA, empresa.trim()); } catch { /* sem storage */ }
      await iniciarSessaoExterna(res.token);
      goto('/');
    } catch (e) {
      erro = e.message === 'Credenciais inválidas'
        ? 'Empresa, usuário ou senha inválidos.'
        : e.message;
    }
  }

  // Usuário cadastrado no DataHub (e-mail e senha).
  async function loginDataHub() {
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
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter') login();
  }
</script>

<svelte:head><title>Login — GPA Analytics</title></svelte:head>

<div class="login-wrap">
  <div class="login-box card">
    <h1>GPA Analytics</h1>
    <p class="subtitle">Analytics Multiempresa</p>

    <label>
      Empresa
      <input type="text" bind:value={empresa} on:keydown={onKeydown} autocapitalize="off" autocomplete="organization"
             placeholder="Código da empresa (usuários do app)" />
    </label>

    <label>
      {empresa.trim() ? 'Usuário' : 'Usuário ou e-mail'}
      <input type="text" bind:value={email} on:keydown={onKeydown} autocapitalize="off" autocomplete="username"
             placeholder={empresa.trim() ? 'Seu usuário do app' : 'admin@datahub.local'} />
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
