<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
  import ApresentacaoPlayer from '$lib/components/ApresentacaoPlayer.svelte';
  import { filtrosEfetivos } from '$lib/apresentacao.js';

  const id = $page.params.id;
  let apresentacao = null;
  let slides = [];
  let rodando = false;
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try {
      const a = await api.executarApresentacao(id);
      apresentacao = a;
      slides = await Promise.all(a.slides.map(async s => ({
        ...s, override: {}, variaveis: await api.variaveisPainel(s.painel.id).catch(() => []),
      })));
    } catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  async function iniciar() {
    try { await document.documentElement.requestFullscreen?.(); } catch { /* segue sem tela cheia */ }
    rodando = true;
  }

  async function sair() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); } catch { /* ignora */ }
    goto('/apresentar');
  }

  function onMudou(slide, detail) {
    slide.override = { ...slide.override, ...detail };
    slides = slides;
  }
</script>

<svelte:head><title>{apresentacao?.nome ?? 'Apresentação'} — GPA Analytics</title></svelte:head>

{#if rodando}
  <ApresentacaoPlayer {apresentacao} bind:slides on:sair={sair} />
{:else}
  <div class="preparo">
    {#if carregando}
      <p class="muted">Carregando...</p>
    {:else if erro}
      <p class="error">{erro}</p>
      <a href="/apresentar" class="btn-ghost">Voltar</a>
    {:else}
      <h2>{apresentacao.nome}</h2>
      {#if apresentacao.descricao}<p class="muted">{apresentacao.descricao}</p>{/if}
      <p class="hint">Ajuste os filtros se quiser (vale só para esta execução) e clique em Iniciar. Os dados são atualizados a cada {Math.round(apresentacao.intervalo_atualizacao_seg / 60)} min.</p>

      {#if slides.length === 0}
        <p class="muted">Nenhum slide cadastrado.</p>
      {:else}
        {#each slides as s, i}
          <div class="slide-card">
            <div class="slide-titulo">Slide {i + 1} — {s.painel.nome} <span class="muted">({s.duracao_seg}s)</span></div>
            {#if s.variaveis.length > 0}
              <div class="filtros-bar">
                {#each s.variaveis as v}
                  <FiltroVariavel variavel={v} valor={filtrosEfetivos(s.filtros, s.override)} on:mudou={(e) => onMudou(s, e.detail)} />
                {/each}
              </div>
            {:else}
              <span class="muted">Sem filtros.</span>
            {/if}
          </div>
        {/each}
      {/if}

      <div class="acoes">
        <a href="/apresentar" class="btn-ghost">Voltar</a>
        <button class="btn-primary" on:click={iniciar} disabled={slides.length === 0}>▶ Iniciar apresentação</button>
      </div>
    {/if}
  </div>
{/if}

<style>
.preparo { padding: 24px; max-width: 960px; margin: 0 auto; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.hint, .muted { color: var(--muted); font-size: 13px; }
.slide-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-top: 12px; }
.slide-titulo { font-weight: 600; color: var(--text); margin-bottom: 10px; }
.filtros-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.acoes { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
a.btn-ghost { display: inline-flex; align-items: center; padding: 8px 14px; border-radius: 6px; text-decoration: none; }
</style>
