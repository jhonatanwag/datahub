<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let empresas   = [];
  let carregando = true;
  let erro       = null;

  onMount(async () => {
    try {
      empresas = await api.listarEmpresas();
    } catch (e) {
      erro = 'Erro ao carregar empresas.';
    } finally {
      carregando = false;
    }
  });

  async function desativar(id) {
    if (!confirm('Desativar esta empresa?')) return;
    try {
      await api.desativarEmpresa(id);
      empresas = empresas.map(e => e.id === id ? { ...e, ativo: false } : e);
    } catch {
      alert('Erro ao desativar empresa.');
    }
  }

  async function reativar(id) {
    if (!confirm('Reativar esta empresa?')) return;
    try {
      await api.reativarEmpresa(id);
      empresas = empresas.map(e => e.id === id ? { ...e, ativo: true } : e);
    } catch {
      alert('Erro ao reativar empresa.');
    }
  }

  function inicial(nome) {
    return nome?.charAt(0)?.toUpperCase() ?? '?';
  }
</script>

<svelte:head><title>Empresas — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Empresas</h2>
    <a href="/configuracoes/empresas/nova" class="btn-primary">+ Nova Empresa</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if empresas.length === 0}
    <p class="muted">Nenhuma empresa cadastrada.</p>
  {:else}
    <div class="grid">
      {#each empresas as empresa}
        <div class="card empresa-card" class:inativo={!empresa.ativo}>
          <div class="card-logo">
            <img
              src={empresa.logo_url || `/api/empresas/${empresa.id}/logo`}
              alt={empresa.nome}
              on:error={(e) => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex'; }}
            />
            <div class="logo-inicial" style="display:none">{inicial(empresa.nome)}</div>
          </div>
          <div class="card-info">
            <strong>{empresa.nome}</strong>
            <span class="muted slug">{empresa.slug}</span>
            <span class="badge" class:ativo={empresa.ativo}>{empresa.ativo ? 'Ativo' : 'Inativo'}</span>
          </div>
          <div class="card-actions">
            <a href="/configuracoes/empresas/{empresa.id}" class="btn-ghost btn-sm">Editar</a>
            {#if empresa.ativo}
              <button class="btn-ghost btn-sm danger" on:click={() => desativar(empresa.id)}>Desativar</button>
            {:else}
              <button class="btn-ghost btn-sm ativo" on:click={() => reativar(empresa.id)}>Ativar</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.empresa-card { display: flex; align-items: center; gap: 16px; padding: 16px; }
.empresa-card.inativo { opacity: .5; }
.card-logo { width: 48px; height: 48px; flex-shrink: 0; position: relative; }
.card-logo img { width: 48px; height: 48px; object-fit: contain; border-radius: 6px; }
.logo-inicial {
  width: 48px; height: 48px;
  background: var(--accent); color: #0d1117;
  font-size: 22px; font-weight: 700;
  border-radius: 6px;
  align-items: center; justify-content: center;
}
.card-info { flex: 1; display: flex; flex-direction: column; gap: 4px; font-size: 13px; min-width: 0; }
.card-info strong { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slug { font-family: var(--font-display); font-size: 11px; }
.card-actions { display: flex; gap: 6px; flex-direction: column; flex-shrink: 0; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); width: fit-content; }
.badge.ativo { background: #1a4731; color: #3fb950; }
.danger { color: var(--danger, #f85149) !important; }
.ativo  { color: #3fb950 !important; }
.muted { color: var(--muted); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
