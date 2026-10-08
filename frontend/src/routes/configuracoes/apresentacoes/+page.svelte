<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let apresentacoes = [];
  let busca = '';
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try { apresentacoes = await api.listarApresentacoes(); }
    catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  $: filtradas = apresentacoes.filter(a =>
    !busca.trim() || a.nome.toLowerCase().includes(busca.trim().toLowerCase()));

  async function desativar(a) {
    if (!confirm(`Desativar apresentação "${a.nome}"?`)) return;
    try {
      await api.desativarApresentacao(a.id);
      apresentacoes = apresentacoes.map(x => x.id === a.id ? { ...x, ativo: false } : x);
    } catch (e) { alert(e.message); }
  }
</script>

<svelte:head><title>Apresentações — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Apresentações</h2>
    <a href="/configuracoes/apresentacoes/nova" class="btn-primary">+ Nova Apresentação</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if apresentacoes.length === 0}
    <p class="muted">Nenhuma apresentação cadastrada.</p>
  {:else}
    <div class="filtros"><input type="text" placeholder="Buscar…" bind:value={busca} /></div>
    <div class="cards-grid">
      {#each filtradas as a}
        <div class="card" class:inativo={!a.ativo}>
          <div class="card-top">
            <span class="card-nome">{a.nome}</span>
            <span class="badge" class:ativo={a.ativo}>{a.ativo ? 'Ativa' : 'Inativa'}</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">slug: <code>{a.slug}</code></span>
            <span class="meta-item">{a.total_slides} slide(s) · atualiza a cada {Math.round(a.intervalo_atualizacao_seg / 60)} min</span>
            <span class="meta-item">{a.empresa_id ? `Empresa #${a.empresa_id}` : 'Todas as empresas'}</span>
            {#if a.descricao}<span class="meta-descricao">{a.descricao}</span>{/if}
          </div>
          <div class="card-actions">
            <a href="/apresentar/{a.id}" class="btn-ghost btn-sm" target="_blank">Apresentar</a>
            <a href="/configuracoes/apresentacoes/{a.id}" class="btn-ghost btn-sm">Editar</a>
            {#if a.ativo}<button class="btn-ghost btn-sm danger" on:click={() => desativar(a)}>Desativar</button>{/if}
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
.filtros { margin-bottom: 16px; }
.filtros input { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; width: 260px; }
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
a.btn-primary { display: inline-flex; align-items: center; padding: 8px 16px; border-radius: 6px; text-decoration: none; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
