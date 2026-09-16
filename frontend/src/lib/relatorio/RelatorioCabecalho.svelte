<script>
  export let titulo = '';
  export let subtitulo = '';
  export let empresaNome = '';
  export let empresaEndereco = '';
  export let empresaCnpj = '';
  export let empresaLogoUrl = null;
  export let filtros = [];   // [{nome, valor}]

  // timeZone fixo: o PDF é renderizado num Chromium headless dentro do
  // container pdf-renderer, cujo relógio do sistema é UTC — sem isso o
  // horário "Emitido em" sai 3h adiantado em relação a Brasília.
  const emitidoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo',
  }).format(new Date());
</script>

<header class="rc">
  <div class="rc-faixa">
    <svg class="rc-arcos" viewBox="0 0 800 150" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <circle cx="720" cy="10"  r="120" fill="#ffffff" opacity="0.04" />
      <circle cx="780" cy="95"  r="95"  fill="#ffffff" opacity="0.05" />
      <circle cx="610" cy="150" r="70"  fill="#ffffff" opacity="0.03" />
    </svg>

    <div class="rc-logo-wrap">
      {#if empresaLogoUrl}
        <img class="rc-logo" src={empresaLogoUrl} alt="" on:error={(e) => (e.target.style.display = 'none')} />
      {/if}
    </div>

    <div class="rc-centro">
      {#if subtitulo}<span class="rc-subtitulo">{subtitulo}</span>{/if}
      <h1 class="rc-titulo">{titulo}</h1>
    </div>

    <div class="rc-empresa">
      <span class="rc-empresa-nome">{empresaNome}</span>
      {#if empresaEndereco}<span class="rc-meta">{empresaEndereco}</span>{/if}
      {#if empresaCnpj}<span class="rc-meta">CNPJ: {empresaCnpj}</span>{/if}
      <span class="rc-meta">Emitido em {emitidoEm}</span>
    </div>
  </div>

  {#if filtros.length}
    <div class="rc-filtros">
      {#each filtros as f}
        <span class="rc-chip"><strong>{f.nome}:</strong> {f.valor}</span>
      {/each}
    </div>
  {/if}
</header>

<style>
  .rc {
    /* conteúdo normal — aparece uma vez no topo do relatório. O cabeçalho que
       se repete em toda página do PDF vem do page.pdf({displayHeaderFooter}). */
    background: #F4F6F2;
  }
  .rc-faixa {
    position: relative; overflow: hidden;
    display: grid; grid-template-columns: auto 1fr auto; align-items: center;
    gap: 18px; padding: 14px 16mm;
    background: linear-gradient(120deg, #1F3D2B, #2E5E3E);
    color: #fff;
  }
  .rc-arcos { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .rc-logo-wrap {
    width: 68px; height: 68px; border-radius: 50%; background: #fff;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0; z-index: 1;
  }
  .rc-logo { width: 54px; height: 54px; object-fit: contain; }
  .rc-centro { z-index: 1; min-width: 0; }
  .rc-subtitulo {
    display: block; font-size: 10px; font-weight: 700; letter-spacing: .14em; color: #BFE3C6;
  }
  .rc-titulo { margin: 2px 0 0; font-size: 21px; font-weight: 700; line-height: 1.15; color: #fff; }
  .rc-empresa { z-index: 1; text-align: right; display: flex; flex-direction: column; gap: 1px; }
  .rc-empresa-nome { font-size: 12px; font-weight: 700; }
  .rc-meta { font-size: 9.5px; color: #DDE8DD; }
  .rc-filtros {
    display: flex; flex-wrap: wrap; gap: 6px; padding: 7px 16mm;
    background: #F4F6F2; border-bottom: 1px solid #BFE3C6;
  }
  .rc-chip {
    font-size: 10px; color: #2B2B2B; background: #E9F3EC;
    border: 1px solid #CFE6D6; border-radius: 999px; padding: 2px 8px;
  }
  .rc-chip strong { color: #8A968A; font-weight: 700; }

  @media print { .rc-faixa { padding: 14px 12mm; } .rc-filtros { padding: 7px 12mm; } }
</style>
