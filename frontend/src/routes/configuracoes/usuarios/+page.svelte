<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import { ordenarLista, proximaDirecao } from '$lib/sort.js';

  let usuarios   = [];
  let carregando = true;
  let erro       = null;
  let ordenarCampo   = null;
  let ordenarDirecao = null;

  const colunas = [
    { label: 'Nome',     campo: 'nome' },
    { label: 'E-mail',   campo: 'email' },
    { label: 'Perfil',   campo: 'role' },
    { label: 'Status',   campo: 'ativo' },
    { label: 'Empresas', campo: null },
    { label: 'Ações',    campo: null },
  ];

  function onClickColuna(campo) {
    if (!campo) return;
    ordenarDirecao = proximaDirecao(campo, ordenarCampo, ordenarDirecao);
    ordenarCampo = ordenarDirecao ? campo : null;
  }

  onMount(async () => {
    try {
      usuarios = await api.listarUsuarios();
    } catch {
      erro = 'Erro ao carregar usuários.';
    } finally {
      carregando = false;
    }
  });

  $: ordenadas = ordenarLista(usuarios, ordenarCampo, ordenarDirecao);

  async function desativar(id) {
    if (!confirm('Desativar este usuário?')) return;
    try {
      await api.desativarUsuario(id);
      usuarios = usuarios.map(u => u.id === id ? { ...u, ativo: false } : u);
    } catch (e) {
      alert(e.message || 'Erro ao desativar.');
    }
  }
</script>

<svelte:head><title>Usuários — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Usuários</h2>
    <a href="/configuracoes/usuarios/novo" class="btn-primary">+ Novo Usuário</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <table>
      <thead>
        <tr>
          {#each colunas as c}
            <th class:sortable={c.campo} on:click={() => onClickColuna(c.campo)}>
              {c.label}{#if ordenarCampo === c.campo}{ordenarDirecao === 'asc' ? ' ▲' : ' ▼'}{/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each ordenadas as u}
          <tr class:inativo={!u.ativo}>
            <td>{u.nome}</td>
            <td>{u.email}</td>
            <td><span class="badge role-{u.role}">{u.role === 'admin' ? 'Admin' : 'Visualizador'}</span></td>
            <td><span class="badge" class:ativo={u.ativo}>{u.ativo ? 'Ativo' : 'Inativo'}</span></td>
            <td class="empresas-cell">{u.empresas?.map(e => e.slug).join(', ') || '—'}</td>
            <td class="actions-cell">
              <a href="/configuracoes/usuarios/{u.id}" class="btn-ghost btn-sm">Editar</a>
              {#if u.ativo}
                <button class="btn-ghost btn-sm danger" on:click={() => desativar(u.id)}>Desativar</button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--muted); border-bottom: 1px solid var(--border); font-weight: 500; }
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--text); }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
tr.inativo td { opacity: .5; }
.actions-cell { display: flex; gap: 8px; }
.empresas-cell { color: var(--muted); font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.badge.ativo { background: #1a4731; color: #3fb950; }
.role-admin { background: #1c2d4a; color: #58a6ff; }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
