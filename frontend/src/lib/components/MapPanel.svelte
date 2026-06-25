<script>
  import { onMount, onDestroy } from 'svelte';

  export let pontos = [];

  let container;
  let map;
  let markers = [];
  let leafletRef = null;

  onMount(async () => {
    const L = (await import('leaflet')).default;
    await import('leaflet/dist/leaflet.css');

    map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19
    }).addTo(map);

    leafletRef = L;
    renderPontos(L);
  });

  $: if (map && leafletRef && pontos) renderPontos(leafletRef);

  function renderPontos(L) {
    markers.forEach(m => m.remove());
    markers = [];
    if (!pontos.length) return;
    const maxVal = Math.max(...pontos.map(p => p.valor), 1);
    pontos.forEach(p => {
      const r = 8 + (p.valor / maxVal) * 22;
      const m = L.circleMarker([p.lat, p.lng], {
        radius: r, fillColor: '#79c0ff', color: '#0d1117',
        fillOpacity: .75, weight: 1.5
      }).bindPopup(`<b>${p.label}</b><br>${p.valor}`).addTo(map);
      markers.push(m);
    });
  }

  onDestroy(() => map?.remove());
</script>

<div bind:this={container} style="width:100%;height:300px;border-radius:8px;overflow:hidden;"></div>
