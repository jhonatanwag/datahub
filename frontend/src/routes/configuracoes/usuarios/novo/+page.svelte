<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let nome     = '';
  let email    = '';
  let senha    = '';
  let role     = 'viewer';
  let empresasDisponiveis  = [];
  let empresasSelecionadas = new Set();
  let salvando = false;
  let erro     = '';

  onMount(async () => {
    try {
      const lista = await api.listarEmpresas();
      empresasDisponiveis = lista.filter(e => e.ativo);
    } catch {
      erro = 'Erro ao carregar empresas.';
    }
  });

  function toggleEmpresa(id) {
    if (empresasSelecionadas.has(id)) empresasSelecionadas.delete(id);
    else empresasSelecionadas.add(id);
    empresasSelecionadas = new Set(empresasSelecionadas);
  }

  async function salvar() {
    erro = '';
    if (!nome || !email || !senha) {
      erro = 'Nome, e-mail e senha são obrigatórios.';
      return;
    }
    if (empresasSelecionadas.size === 0) {
      erro = 'Selecione ao menos uma empresa.';
      return;
    }
    salvando = true;
    try {
      const u = await api.criarUsuario({ nome, email, senha, role });
      await api.vincularEmpresas(u.id, [...empresasSelecionadas]);
      goto('/configuracoes/usuarios');
    } catch (e) {
      erro = e.message || 'Erro ao salvar usuário.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Novo Usuário — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Novo Usuário</h2>
    <a href="/configuracoes/usuarios" class="btn-ghost">← Voltar</a>
  </div>

  <div class="form card">
    <label>
      Nome completo
      <input bind:value={nome} placeholder="João da Silva" required />
    </label>
    <label>
      E-mail
      <input type="email" bind:value={email} placeholder="joao@empresa.com" required />
    </label>
    <label>
      Senha
      <input type="password" bind:value={senha} required />
    </label>
    <label>
      Perfil
      <select bind:value={role}>
        <option value="viewer">Visualizador</option>
        <option value="admin">Admin</option>
      </select>
    </label>

    <fieldset>
      <legend>Empresas com acesso</legend>
      {#each empresasDisponiveis as empresa}
        <label class="checkbox-label">
          <input
            type="checkbox"
            checked={empresasSelecionadas.has(empresa.id)}
            on:change={() => toggleEmpresa(empresa.id)}
          />
          {empresa.nome}
        </label>
      {/each}
      {#if empresasDisponiveis.length === 0}
        <p class="empty-msg">Nenhuma empresa disponível.</p>
      {/if}
    </fieldset>

    {#if erro}<p class="error">{erro}</p>{/if}

    <div class="actions">
      <a href="/configuracoes/usuarios" class="btn-ghost">Cancelar</a>
      <button
        class="btn-primary"
        on:click={salvar}
        disabled={salvando || !nome || !email || !senha}
      >
        {salvando ? 'Salvando...' : 'Salvar Usuário'}
      </button>
    </div>
  </div>
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.form { max-width: 480px; display: flex; flex-direction: column; gap: 16px; padding: 24px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
legend { font-size: 13px; color: var(--muted); padding: 0 4px; }
.checkbox-label { flex-direction: row; align-items: center; gap: 8px; cursor: pointer; color: var(--text); }
.empty-msg { font-size: 12px; color: var(--muted); margin: 0; }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
