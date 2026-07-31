<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { token, usuario, empresaAtiva } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';

  let nomeUsuario = '';
  let empresas    = [];
  let erro        = '';
  let carregando  = false;

  onMount(() => {
    const raw = typeof sessionStorage !== 'undefined'
      ? sessionStorage.getItem('temp_user')
      : null;
    if (!raw) { goto('/login'); return; }

    const tempUser = JSON.parse(raw);
    nomeUsuario = tempUser.nome;
    empresas    = tempUser.empresas;

    if (empresas.length === 1) selecionar(empresas[0]).catch(() => {});
  });

  async function selecionar(empresa) {
    const raw = sessionStorage.getItem('temp_user');
    if (!raw) { goto('/login'); return; }
    const tempUser = JSON.parse(raw);

    carregando = true;
    erro = '';
    try {
      const res = await api.selecionarEmpresa(tempUser.session_token, empresa.id);
      token.set(res.token);
      // Fetch full user profile (includes role from JWT-validated session)
      const me = await api.me();
      usuario.set(me);
      empresaAtiva.set({ id: empresa.id, slug: empresa.slug, nome: empresa.nome, logo_url: empresa.logo_url, url_impressao_base: me.url_impressao_base ?? null });
      sessionStorage.removeItem('temp_user');
      goto('/');
    } catch {
      erro = 'Erro ao selecionar empresa. Tente novamente.';
      carregando = false;
    }
  }

  function sair() {
    sessionStorage.removeItem('temp_user');
    goto('/login');
  }

  function inicial(nome) {
    return nome?.charAt(0)?.toUpperCase() ?? '?';
  }
</script>

<svelte:head><title>Selecionar Empresa — GPA Analytics</title></svelte:head>

<div class="wrap">
  <div class="header">
    <h2>Olá, {nomeUsuario}! Selecione a empresa:</h2>
    <button class="btn-ghost" on:click={sair}>Sair</button>
  </div>

  {#if erro}<p class="error">{erro}</p>{/if}

  {#if empresas.length === 0}
    <p class="sem-empresa">Sua conta não tem acesso a nenhuma empresa. Contate o administrador.</p>
  {/if}

  <div class="grid">
    {#each empresas as empresa (empresa.id)}
      <button
        class="card empresa-card"
        on:click={() => selecionar(empresa)}
        disabled={carregando}
      >
        <div class="logo-wrap">
          <img
            src={empresa.logo_url}
            alt={empresa.nome}
            on:error={(e) => { e.target.style.display = 'none'; e.target.nextElementSibling.style.display = 'flex'; }}
          />
          <div class="logo-inicial" style="display:none">{inicial(empresa.nome)}</div>
        </div>
        <span class="empresa-nome">{empresa.nome}</span>
      </button>
    {/each}
  </div>
</div>

<style>
.wrap {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 32px;
}
.header {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 32px;
}
h2 { font-size: 20px; color: var(--text); }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
  width: 100%;
  max-width: 720px;
}
.empresa-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 16px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color .15s, transform .1s;
  text-align: center;
}
.empresa-card:hover { border-color: var(--accent-blue); transform: translateY(-2px); }
.logo-wrap { width: 64px; height: 64px; position: relative; }
.logo-wrap img { width: 64px; height: 64px; object-fit: contain; border-radius: 8px; }
.logo-inicial {
  width: 64px; height: 64px;
  background: var(--accent);
  color: white;
  font-size: 28px;
  font-weight: 700;
  border-radius: 8px;
  align-items: center;
  justify-content: center;
}
.empresa-nome { font-size: 14px; color: var(--text); font-weight: 500; }
.error { color: var(--danger, #f85149); margin-bottom: 16px; }
.sem-empresa { color: var(--muted); font-size: 14px; text-align: center; max-width: 400px; }
</style>
