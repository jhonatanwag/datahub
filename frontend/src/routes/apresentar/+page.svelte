<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let lista = [];
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try { lista = await api.minhasApresentacoes(); }
    catch (e) { erro = e.message; }
    finally { carregando = false; }
  });
</script>

<svelte:head><title>Apresentar painéis — GPA Analytics</title></svelte:head>

<div class="page">
  <h2>Apresentar painéis</h2>
  <p class="intro">Escolha uma apresentação para exibir em tela cheia.</p>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if lista.length === 0}
    <p class="muted">Nenhuma apresentação disponível para você.</p>
  {:else}
    <div class="cards-grid">
      {#each lista as a}
        <a class="card" href="/apresentar/{a.id}">
          <span class="card-nome">{a.nome}</span>
          {#if a.descricao}<span class="meta">{a.descricao}</span>{/if}
          <span class="meta">{a.total_slides} slide(s)</span>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.intro { color: var(--muted); font-size: 13px; margin: 4px 0 20px; }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.card { display: flex; flex-direction: column; gap: 6px; padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; text-decoration: none; }
.card:hover { border-color: var(--accent); }
.card-nome { font-size: 15px; font-weight: 600; color: var(--text); }
.meta { font-size: 12px; color: var(--muted); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
