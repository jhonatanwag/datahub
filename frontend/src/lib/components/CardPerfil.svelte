<script>
  // Card (query tipo `card`): 1 linha de resultado, dois modos.
  //
  // Modo perfil — quando existe a coluna `titulo`:
  //   titulo / subtitulo → nome e linha de apoio ao lado do avatar
  //   imagem_url         → caminho de API (ex.: /api/imagens/tipo-veiculo/3) carregado com o token
  //                        da sessão e exibido no avatar; sem ela (ou se falhar) vira iniciais
  //   demais colunas     → campos rótulo/valor (o nome da coluna é o rótulo)
  // Modo lista — sem a coluna `titulo`: cada coluna vira uma linha rótulo/valor; com uma única
  //   coluna, o valor aparece num quadro de nota (ex.: Observações).
  // Em qualquer modo, a coluna "status" vira badge (verde se ATIVO/ATIVA).
  import { onDestroy, createEventDispatcher } from 'svelte';
  import { assetUrl } from '$lib/api.js';

  export let dados = null;
  export let vazio = 'Nenhum registro selecionado.';

  const dispatch = createEventDispatcher();
  const RESERVADAS = ['titulo', 'subtitulo', 'imagem_url'];

  let imagemBlob = null;
  let imagemCarregada = null; // última imagem_url resolvida (evita refetch)

  $: linha  = dados ?? null;
  $: modoLista = linha && !('titulo' in linha);
  $: campos = linha
    ? Object.entries(linha).filter(([k]) => !RESERVADAS.includes(k))
    : [];
  $: carregarImagem(linha?.imagem_url ?? null);

  async function carregarImagem(path) {
    if (path === imagemCarregada) return;
    imagemCarregada = path;
    if (imagemBlob) { URL.revokeObjectURL(imagemBlob); imagemBlob = null; }
    if (!path) { dispatch('pronto'); return; }
    try {
      const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
      const res = await fetch(assetUrl(path), { headers: tok ? { Authorization: `Bearer ${tok}` } : {} });
      if (res.ok && path === imagemCarregada) imagemBlob = URL.createObjectURL(await res.blob());
    } catch { /* sem imagem: mantém as iniciais */ }
    dispatch('pronto');
  }

  onDestroy(() => { if (imagemBlob) URL.revokeObjectURL(imagemBlob); });

  const ehStatus = (k) => k.toLowerCase() === 'status';
  const ehAtivo  = (v) => ['ativo', 'ativa'].includes(String(v ?? '').toLowerCase());
  const iniciais = (t) => String(t ?? '?').trim().split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase();
</script>

{#if !linha}
  <div class="perfil-vazio">
    <div class="perfil-vazio-icone">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h2"/><circle cx="17" cy="17" r="3"/><line x1="21" y1="21" x2="19.2" y2="19.2"/>
      </svg>
    </div>
    <p>{vazio}</p>
  </div>

{:else if modoLista}
  {#if campos.length === 1 && !ehStatus(campos[0][0])}
    <div class="nota">{campos[0][1] ?? '—'}</div>
  {:else}
    <div class="lista">
      {#each campos as [rotulo, valor]}
        <div class="lista-linha">
          <div class="lista-rotulo">{rotulo}</div>
          {#if ehStatus(rotulo)}
            <span class="badge" class:ativo={ehAtivo(valor)}><span class="ponto"></span>{String(valor ?? '—').toUpperCase()}</span>
          {:else}
            <div class="lista-valor">{valor ?? '—'}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

{:else}
  <div class="perfil">
    <div class="perfil-topo">
      <div class="perfil-avatar" aria-hidden="true">
        {#if imagemBlob}
          <img src={imagemBlob} alt="" />
        {:else}
          {iniciais(linha.titulo)}
        {/if}
      </div>
      <div>
        <div class="perfil-nome">{linha.titulo ?? '—'}</div>
        {#if linha.subtitulo}<div class="perfil-sub">{linha.subtitulo}</div>{/if}
      </div>
    </div>
    {#if campos.length}
      <div class="perfil-campos">
        {#each campos as [rotulo, valor]}
          <div class="perfil-campo">
            <div class="perfil-rotulo">{rotulo}</div>
            {#if ehStatus(rotulo)}
              <span class="badge" class:ativo={ehAtivo(valor)}>
                <span class="ponto"></span>{String(valor ?? '—').toUpperCase()}
              </span>
            {:else}
              <div class="perfil-valor">{valor ?? '—'}</div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
.perfil { display: flex; flex-direction: column; gap: 16px; padding: 14px 16px; }
.perfil-topo { display: flex; align-items: center; gap: 16px; }
.perfil-avatar {
  width: 72px; height: 72px; border-radius: 50%; flex-shrink: 0; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: var(--surface2); color: var(--muted);
  font-family: var(--font-display); font-size: 22px; font-weight: 600;
}
.perfil-avatar img { width: 100%; height: 100%; object-fit: cover; }
.perfil-nome { font-size: 18px; font-weight: 600; color: var(--text); }
.perfil-sub  { font-size: 13px; color: var(--muted); margin-top: 2px; }
.perfil-campos {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 16px;
  border-top: 1px solid var(--border); padding-top: 14px;
}
.perfil-rotulo { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.perfil-valor  { font-size: 13px; color: var(--muted); word-break: break-word; }

.lista { display: flex; flex-direction: column; padding: 4px 16px; }
.lista-linha {
  display: grid; grid-template-columns: 42% 1fr; gap: 12px; align-items: center;
  padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px;
}
.lista-linha:last-child { border-bottom: 0; }
.lista-rotulo { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.lista-valor  { color: var(--text); word-break: break-word; }

.nota {
  background: var(--surface2); border-radius: 6px; padding: 12px 14px; margin: 14px 16px;
  font-size: 13px; color: var(--text); white-space: pre-wrap; word-break: break-word;
}

.badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: var(--surface2); color: var(--muted);
}
.badge .ponto { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.badge.ativo  { background: rgba(34, 160, 107, .15); color: #1f9d63; }

.perfil-vazio {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 28px 12px; color: var(--muted); font-size: 13px; text-align: center;
}
.perfil-vazio-icone {
  width: 52px; height: 52px; border-radius: 50%; background: var(--surface2);
  display: flex; align-items: center; justify-content: center;
}
.perfil-vazio-icone svg { width: 24px; height: 24px; }
</style>
