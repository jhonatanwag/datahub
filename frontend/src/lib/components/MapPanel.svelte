<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { usuario } from '$lib/stores/auth.js';
  import { assetUrl } from '$lib/api.js';
  import { idsTiposComImagem, htmlPopup, htmlMarcadorFoto } from '$lib/mapaMarcadores.js';

  export let pontos = [];
  export let camada = 'padrao';
  export let altura = 300;         // px — o PainelGrid passa 300 × row_span do indicador
  export let temaForcado = null;   // 'claro' | 'escuro' | null — força a camada de tiles no relatório

  const dispatch = createEventDispatcher();

  $: temaEfetivo = temaForcado ?? $usuario?.tema ?? 'escuro';

  let container;
  let map;
  let markers = [];
  let leafletRef = null;
  let tileLayer = null;
  let temaAtual = null;
  let camadaAtiva = camada;

  const TILE_URLS = {
    escuro:   'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    claro:    'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    satelite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  };
  const MARKER_STROKE = { escuro: '#0d1117', claro: '#ffffff' };
  const FOTO_BORDA = { escuro: '#3FCF9F', claro: '#1FA97C' };   // borda da foto = destaque do tema
  const TAMANHO_FOTO = 44;

  // Fotos do tipo de equipamento (coluna opcional `tip_veic_id` nos pontos): o endpoint exige
  // o token, então busca-se uma vez por tipo e reaproveita-se o blob entre os marcadores.
  const imagens = {};            // { [tip_veic_id]: blobUrl | null (sem foto) }
  const emVoo = {};
  let imagensPromise = Promise.resolve();
  let geracao = 0;

  function buscarImagem(id) {
    if (id in imagens) return Promise.resolve();
    if (emVoo[id]) return emVoo[id];
    emVoo[id] = (async () => {
      try {
        const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
        const res = await fetch(assetUrl(`/api/imagens/tipo-veiculo/${id}`), { headers: tok ? { Authorization: `Bearer ${tok}` } : {} });
        imagens[id] = res.ok ? URL.createObjectURL(await res.blob()) : null;
      } catch { imagens[id] = null; }
    })();
    return emVoo[id];
  }

  function carregarImagens(pts) {
    return Promise.all(idsTiposComImagem(pts).map(buscarImagem));
  }

  // Só avisa "pronto" (o relatório PDF espera esse evento) depois das fotos carregadas.
  async function avisarPronto() {
    try { await imagensPromise; } catch { /* segue sem fotos */ }
    dispatch('pronto');
  }

  async function atualizar(L) {
    const minha = ++geracao;
    imagensPromise = carregarImagens(pontos);
    await imagensPromise;
    if (minha !== geracao || !map) return;   // chegou outro conjunto de pontos (ou o mapa foi destruído)
    renderPontos(L);
  }

  onMount(async () => {
    const L = (await import('leaflet')).default;
    await import('leaflet/dist/leaflet.css');

    map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);

    leafletRef = L;
    aplicarTileLayer(L, temaEfetivo);
    atualizar(L);
    map.whenReady(() => {
      setTimeout(() => { map.invalidateSize(); avisarPronto(); }, 400);
    });
  });

  $: if (map && leafletRef && temaEfetivo && temaEfetivo !== temaAtual) {
    aplicarTileLayer(leafletRef, temaEfetivo);
    renderPontos(leafletRef);
  }

  $: if (map && leafletRef && pontos) atualizar(leafletRef);

  function aplicarTileLayer(L, tema) {
    if (tileLayer) tileLayer.remove();
    const url = camadaAtiva === 'satelite' ? TILE_URLS.satelite : (TILE_URLS[tema] ?? TILE_URLS.escuro);
    tileLayer = L.tileLayer(url, { maxZoom: 19 }).addTo(map);
    tileLayer.once('load', () => avisarPronto());
    temaAtual = tema;
  }

  function alternarCamada() {
    camadaAtiva = camadaAtiva === 'satelite' ? 'padrao' : 'satelite';
    aplicarTileLayer(leafletRef, temaEfetivo);
    renderPontos(leafletRef);
  }

  function renderPontos(L) {
    markers.forEach(m => m.remove());
    markers = [];
    if (!pontos.length) {
      map.setView([-15.8, -47.9], 4);
      return;
    }
    const corContorno = MARKER_STROKE[temaAtual] ?? MARKER_STROKE.escuro;
    const maxVal = Math.max(...pontos.map(p => Number(p.valor) || 0), 1);
    const bordaFoto = camadaAtiva === 'satelite' ? '#ffffff' : (FOTO_BORDA[temaAtual] ?? FOTO_BORDA.escuro);
    pontos.forEach(p => {
      const foto = imagens[Number(p.tip_veic_id)];
      let m;
      if (foto) {
        const t = TAMANHO_FOTO;
        m = L.marker([p.lat, p.lng], {
          icon: L.divIcon({
            className: 'mp-foto-wrap', html: htmlMarcadorFoto(foto, bordaFoto, t),
            iconSize: [t, t], iconAnchor: [t / 2, t / 2], popupAnchor: [0, -t / 2],
          }),
        });
      } else {
        const r = 8 + ((Number(p.valor) || 0) / maxVal) * 22;
        m = L.circleMarker([p.lat, p.lng], {
          radius: r, fillColor: '#79c0ff', color: corContorno,
          fillOpacity: .75, weight: 1.5
        });
      }
      m.bindPopup(htmlPopup(p)).addTo(map);
      markers.push(m);
    });
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds(), { padding: [32, 32], maxZoom: 12 });
  }

  onDestroy(() => {
    map?.remove();
    Object.values(imagens).forEach(u => { if (u) URL.revokeObjectURL(u); });
  });
</script>

<div class="map-wrap" style="height:{altura}px">
  <div bind:this={container} class="map-container"></div>
  <button class="camada-toggle no-print" on:click={alternarCamada}>
    {camadaAtiva === 'satelite' ? 'Padrão' : 'Satélite'}
  </button>
</div>

<style>
.map-wrap { position: relative; width: 100%; }
.map-container { width: 100%; height: 100%; border-radius: 8px; overflow: hidden; }
.camada-toggle {
  position: absolute; top: 8px; right: 8px; z-index: 1000;
  font-size: 11px; padding: 4px 10px; border-radius: 4px;
  border: 1px solid rgba(0,0,0,.25); background: rgba(255,255,255,.9); color: #111;
  cursor: pointer; font-family: inherit;
}
.camada-toggle:hover { background: #fff; }
:global(.mp-foto-wrap) { background: none; border: none; }
:global(.mp-foto) {
  box-sizing: border-box; width: 100%; height: 100%;
  border: 3px solid; border-radius: 50%; background: #fff; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, .35);
}
:global(.mp-foto img) { display: block; width: 100%; height: 100%; object-fit: contain; padding: 2px; }
:global(.mp-detalhe) { color: #6c7b8f; font-size: 11px; }
</style>
