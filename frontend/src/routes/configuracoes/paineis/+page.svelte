<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let paineis    = [];
  let carregando = true;
  let erro       = null;

  onMount(async () => {
    try {
      paineis = await api.listarPaineis();
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  async function desativar(p) {
    if (!confirm(`Desativar painel "${p.nome}"?`)) return;
    try {
      await api.desativarPainel(p.id);
      paineis = paineis.map(x => x.id === p.id ? { ...x, ativo: false } : x);
    } catch (e) {
      alert(e.message);
    }
  }
</script>

<svelte:head><title>Painéis — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Painéis</h2>
    <a href="/configuracoes/paineis/novo" class="btn-primary">+ Novo Painel</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if paineis.length === 0}
    <p class="muted">Nenhum painel cadastrado.</p>
  {:else}
    <div class="cards-grid">
      {#each paineis as p}
        <div class="card" class:inativo={!p.ativo}>
          <div class="card-top">
            <span class="card-nome">{p.nome}</span>
            <span class="badge" class:ativo={p.ativo}>{p.ativo ? 'Ativo' : 'Inativo'}</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">slug: <code>{p.slug}</code></span>
            <span class="meta-item">{p.colunas} colunas</span>
            <span class="meta-item">{p.empresa_id ? `Empresa #${p.empresa_id}` : 'Global'}</span>
            {#if p.descricao}<span class="meta-descricao">{p.descricao}</span>{/if}
          </div>
          <div class="card-actions">
            <a href="/painel/{p.slug}" class="btn-ghost btn-sm" target="_blank">Ver painel</a>
            <a href="/configuracoes/paineis/{p.id}" class="btn-ghost btn-sm">Editar</a>
            {#if p.ativo}
              <button class="btn-ghost btn-sm danger" on:click={() => desativar(p)}>Desativar</button>
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
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.card.inativo { opacity: .5; }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; }
.card-nome { font-size: 15px; font-weight: 600; color: var(--text); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.badge.ativo { background: #1a4731; color: #3fb950; }
.card-meta { display: flex; flex-direction: column; gap: 4px; }
.meta-item { font-size: 12px; color: var(--muted); }
.meta-item code { font-family: var(--font-display); color: var(--accent-blue); }
.meta-descricao { font-size: 12px; color: var(--muted); font-style: italic; }
.card-actions { display: flex; gap: 8px; }
.danger { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
