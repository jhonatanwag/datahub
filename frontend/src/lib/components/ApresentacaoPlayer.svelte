<script>
  import { onMount, onDestroy, createEventDispatcher, tick } from 'svelte';
  import { api } from '$lib/api.js';
  import { token } from '$lib/stores/auth.js';
  import PainelGrid from '$lib/components/PainelGrid.svelte';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
  import {
    planoRolagem, posicaoRolagem, proximoIndice, anteriorIndice,
    precisaAtualizar, filtrosEfetivos, RENOVAR_TOKEN_MS,
  } from '$lib/apresentacao.js';

  export let apresentacao;
  export let slides;
  const dispatch = createEventDispatcher();

  let indice = 0;
  let dados = {};                 // { [slideId]: { indicadores, urlImpressaoBase, atualizadoEm } }
  let avisoAtualizacao = null;    // string | null
  let pausado = false;
  let filtrosAbertos = false;
  let controlesVisiveis = false;
  let viewport, conteudo;
  let plano = { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: 30 };
  let decorrido = 0;
  let raf, ultimoFrame = 0;
  let timerAtualizar, timerToken, timerControles, observador, wakeLock;

  $: slide = slides[indice];
  $: dadosSlide = slide ? dados[slide.id] : null;
  $: parado = pausado || filtrosAbertos;
  $: filtrosVigentes = slide ? filtrosEfetivos(slide.filtros, slide.override) : {};
  $: filtrosQuery = new URLSearchParams(filtrosVigentes).toString();

  const horaDe = (ms) => new Date(ms).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  async function carregar(s) {
    try {
      const r = await api.renderizarPainel(s.painel.id, filtrosEfetivos(s.filtros, s.override));
      dados = { ...dados, [s.id]: { indicadores: r.indicadores, urlImpressaoBase: r.url_impressao_base, atualizadoEm: Date.now() } };
      avisoAtualizacao = null;
    } catch (e) {
      // mantém o que já está na tela; só avisa
      avisoAtualizacao = `Sem atualizar desde ${horaDe(dados[s.id]?.atualizadoEm ?? Date.now())}`;
    }
  }

  function recalcularPlano() {
    if (!viewport || !slide) return;
    const novo = planoRolagem({
      alturaConteudo: viewport.scrollHeight, alturaViewport: viewport.clientHeight, duracaoSeg: slide.duracao_seg,
    });
    // evita "pulo" por variações mínimas de altura durante a rolagem
    if (novo.rola === plano.rola && Math.abs(novo.distancia - plano.distancia) < 4) return;
    plano = novo;
  }

  async function irPara(novo) {
    indice = novo;
    decorrido = 0;
    await tick();
    if (viewport) viewport.scrollTop = 0;
    plano = { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: slide?.duracao_seg ?? 30 };
    recalcularPlano();
    const d = dados[slide.id];
    if (!d || precisaAtualizar(d.atualizadoEm, Date.now(), apresentacao.intervalo_atualizacao_seg)) carregar(slide);
  }

  const avancar = () => irPara(proximoIndice(indice, slides.length));
  const voltar  = () => irPara(anteriorIndice(indice, slides.length));

  function quadro(agora) {
    raf = requestAnimationFrame(quadro);
    const dt = ultimoFrame ? Math.min((agora - ultimoFrame) / 1000, 2) : 0;
    ultimoFrame = agora;
    if (parado || !slide) return;
    decorrido += dt;
    if (viewport) viewport.scrollTop = posicaoRolagem(plano, decorrido);
    if (decorrido >= plano.tempoTotalSeg) avancar();
  }

  function mostrarControles() {
    controlesVisiveis = true;
    clearTimeout(timerControles);
    timerControles = setTimeout(() => { if (!filtrosAbertos) controlesVisiveis = false; }, 4000);
  }

  async function aplicarFiltros() {
    filtrosAbertos = false;
    await carregar(slide);
  }

  function restaurarFiltros() { slide.override = {}; slides = slides; }

  function aoMudarFiltro(detail) {
    slide.override = { ...slide.override, ...detail };
    slides = slides;
  }

  onMount(async () => {
    if (slides.length === 0) return;
    await carregar(slides[0]);
    await irPara(0);
    observador = new ResizeObserver(recalcularPlano);
    observador.observe(conteudo);
    raf = requestAnimationFrame(quadro);
    // recarrega o slide em exibição no intervalo configurado
    timerAtualizar = setInterval(() => slide && carregar(slide), apresentacao.intervalo_atualizacao_seg * 1000);
    // renova o token pra TV não cair em "sessão expirada"
    timerToken = setInterval(async () => {
      try { token.set((await api.renovarToken()).token); }
      catch (e) { console.error('Falha ao renovar token:', e); }
    }, RENOVAR_TOKEN_MS);
    try { wakeLock = await navigator.wakeLock?.request('screen'); } catch { /* sem wake lock, segue */ }
  });

  onDestroy(() => {
    if (typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(raf);
    clearInterval(timerAtualizar);
    clearInterval(timerToken);
    clearTimeout(timerControles);
    observador?.disconnect();
    try { wakeLock?.release(); } catch { /* ignora */ }
  });
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="player" class:sem-cursor={!controlesVisiveis} on:mousemove={mostrarControles} on:touchstart={mostrarControles}>
  {#if slides.length === 0}
    <p class="vazio">Nenhum slide cadastrado.</p>
  {:else}
    <div class="topo">
      <span class="topo-titulo">{slide?.painel.nome}</span>
      <span class="topo-info">
        {#if avisoAtualizacao}<span class="aviso">{avisoAtualizacao}</span>{/if}
        Slide {indice + 1} de {slides.length}{pausado ? ' · pausado' : ''}
      </span>
    </div>

    <div class="viewport" bind:this={viewport}>
      <div class="conteudo" bind:this={conteudo}>
        {#if dadosSlide}
          <PainelGrid
            painel={slide.painel}
            indicadores={dadosSlide.indicadores}
            slug={slide.painel.slug}
            filtrosAtivos={filtrosVigentes}
            {filtrosQuery}
            urlImpressaoBase={dadosSlide.urlImpressaoBase}
          />
        {:else}
          <p class="vazio">{avisoAtualizacao ?? 'Carregando…'}</p>
        {/if}
      </div>
    </div>
  {/if}

  <div class="controles" class:visivel={controlesVisiveis || filtrosAbertos}>
    {#if filtrosAbertos && slide}
      <div class="painel-filtros">
        {#each slide.variaveis as v}
          <FiltroVariavel variavel={v} valor={filtrosVigentes} on:mudou={(e) => aoMudarFiltro(e.detail)} />
        {:else}
          <span class="muted">Este painel não tem filtros.</span>
        {/each}
        <div class="acoes-filtros">
          <button class="btn-ghost" on:click={restaurarFiltros}>Restaurar padrão</button>
          <button class="btn-primary" on:click={aplicarFiltros}>Aplicar</button>
        </div>
      </div>
    {/if}
    <div class="barra">
      <button class="btn-ghost" on:click={voltar} title="Slide anterior">‹</button>
      <button class="btn-ghost" on:click={() => pausado = !pausado}>{pausado ? '▶ Continuar' : '⏸ Pausar'}</button>
      <button class="btn-ghost" on:click={avancar} title="Próximo slide">›</button>
      <button class="btn-ghost" on:click={() => filtrosAbertos = !filtrosAbertos}>Filtros</button>
      <button class="btn-ghost danger" on:click={() => dispatch('sair')}>Sair</button>
    </div>
  </div>
</div>

<style>
.player { position: fixed; inset: 0; background: var(--bg); display: flex; flex-direction: column; z-index: 50; }
.sem-cursor { cursor: none; }
.topo { display: flex; justify-content: space-between; align-items: baseline; padding: 10px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.topo-titulo { font-family: var(--font-display); font-size: 18px; color: var(--text); }
.topo-info { font-size: 13px; color: var(--muted); display: flex; gap: 12px; }
.aviso { color: var(--accent-orange); }
.viewport { flex: 1; overflow: hidden; padding: 16px 24px; }
.vazio { padding: 48px; text-align: center; color: var(--muted); font-size: 18px; }
.controles { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; opacity: 0; pointer-events: none; transition: opacity .25s; z-index: 60; }
.controles.visivel { opacity: 1; pointer-events: auto; }
.barra { display: flex; gap: 6px; padding: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,.35); }
.painel-filtros { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; max-width: min(720px, 92vw); padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,.35); }
.acoes-filtros { display: flex; gap: 8px; margin-left: auto; }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); font-size: 13px; }
@media (min-width: 1920px) { .viewport { padding: 24px 36px; } .topo-titulo { font-size: 26px; } .topo-info { font-size: 16px; } }
</style>
