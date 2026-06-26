<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let usuario              = null;
  let empresasDisponiveis  = [];
  let empresasSelecionadas = new Set();
  let salvando = false;
  let erro     = '';

  onMount(async () => {
    try {
      const id = Number($page.params.id);
      const [todos, todas, vinculadas] = await Promise.all([
        api.listarUsuarios(),
        api.listarEmpresas(),
        api.listarEmpresasUsuario(id)
      ]);
      const u = todos.find(u => u.id === id);
      if (!u) { goto('/configuracoes/usuarios'); return; }
      usuario = { ...u, senha: '' };
      empresasDisponiveis  = todas.filter(e => e.ativo);
      empresasSelecionadas = new Set(vinculadas.map(e => e.id));
    } catch {
      goto('/configuracoes/usuarios');
    }
  });

  function toggleEmpresa(id) {
    if (empresasSelecionadas.has(id)) empresasSelecionadas.delete(id);
    else empresasSelecionadas.add(id);
    empresasSelecionadas = new Set(empresasSelecionadas);
  }

  async function salvar() {
    erro = '';
    salvando = true;
    try {
      const body = {
        nome:  usuario.nome,
        email: usuario.email,
        senha: usuario.senha || 'UNCHANGED',
        role:  usuario.role,
        ativo: usuario.ativo
      };
      await api.atualizarUsuario(usuario.id, body);
      await api.vincularEmpresas(usuario.id, [...empresasSelecionadas]);
      goto('/configuracoes/usuarios');
    } catch (e) {
      erro = e.message || 'Erro ao salvar.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Editar Usuário — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Editar Usuário</h2>
    <a href="/configuracoes/usuarios" class="btn-ghost">← Voltar</a>
  </div>

  {#if usuario}
    <div class="form card">
      <label>
        Nome completo
        <input bind:value={usuario.nome} required />
      </label>
      <label>
        E-mail
        <input type="email" bind:value={usuario.email} required />
      </label>
      <label>
        Nova senha (deixe em branco para manter)
        <input type="password" bind:value={usuario.senha} placeholder="••••••••" />
      </label>
      <label>
        Perfil
        <select bind:value={usuario.role}>
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
        <button class="btn-primary" on:click={salvar} disabled={salvando}>
          {salvando ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </div>
    </div>
  {:else}
    <p class="muted">Carregando...</p>
  {/if}
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
.muted { color: var(--muted); }
</style>
