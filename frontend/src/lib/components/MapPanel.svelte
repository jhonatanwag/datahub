<script>
  import { onMount, onDestroy } from 'svelte';
  import { usuario } from '$lib/stores/auth.js';

  export let pontos = [];
  export let camada = 'padrao';

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

  onMount(async () => {
    const L = (await import('leaflet')).default;
    await import('leaflet/dist/leaflet.css');

    map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);

    leafletRef = L;
    aplicarTileLayer(L, $usuario?.tema ?? 'escuro');
    renderPontos(L);
  });

  $: if (map && leafletRef && $usuario?.tema && $usuario.tema !== temaAtual) {
    aplicarTileLayer(leafletRef, $usuario.tema);
    renderPontos(leafletRef);
  }

  $: if (map && leafletRef && pontos) renderPontos(leafletRef);

  function aplicarTileLayer(L, tema) {
    if (tileLayer) tileLayer.remove();
    const url = camadaAtiva === 'satelite' ? TILE_URLS.satelite : (TILE_URLS[tema] ?? TILE_URLS.escuro);
    tileLayer = L.tileLayer(url, { maxZoom: 19 }).addTo(map);
    temaAtual = tema;
  }

  function alternarCamada() {
    camadaAtiva = camadaAtiva === 'satelite' ? 'padrao' : 'satelite';
    aplicarTileLayer(leafletRef, $usuario?.tema ?? 'escuro');
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
    pontos.forEach(p => {
      const r = 8 + ((Number(p.valor) || 0) / maxVal) * 22;
      const m = L.circleMarker([p.lat, p.lng], {
        radius: r, fillColor: '#79c0ff', color: corContorno,
        fillOpacity: .75, weight: 1.5
      }).bindPopup(`<b>${p.label}</b><br>${p.valor}`).addTo(map);
      markers.push(m);
    });
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds(), { padding: [32, 32], maxZoom: 12 });
  }

  onDestroy(() => map?.remove());
</script>

<div class="map-wrap">
  <div bind:this={container} class="map-container"></div>
  <button class="camada-toggle" on:click={alternarCamada}>
    {camadaAtiva === 'satelite' ? 'Padrão' : 'Satélite'}
  </button>
</div>

<style>
.map-wrap { position: relative; width: 100%; height: 300px; }
.map-container { width: 100%; height: 100%; border-radius: 8px; overflow: hidden; }
.camada-toggle {
  position: absolute; top: 8px; right: 8px; z-index: 1000;
  font-size: 11px; padding: 4px 10px; border-radius: 4px;
  border: 1px solid rgba(0,0,0,.25); background: rgba(255,255,255,.9); color: #111;
  cursor: pointer; font-family: inherit;
}
.camada-toggle:hover { background: #fff; }
</style>
