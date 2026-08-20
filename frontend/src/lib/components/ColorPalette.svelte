<script>
  export let value = '';

  // Paleta de referência do tema escuro (padrão) do app.css — fixa, não
  // reage ao tema do usuário logado, já que a cor do KPI é um hex estático
  // salvo por query, não uma variável de tema.
  const CORES = [
    { nome: 'bg',             hex: '#071F15' },
    { nome: 'surface',        hex: '#0F2E20' },
    { nome: 'border',         hex: '#2B5A45' },
    { nome: 'text',           hex: '#F3F8F5' },
    { nome: 'muted',          hex: '#A4B7AE' },
    { nome: 'accent',         hex: '#3DBE67' },
    { nome: 'accent-blue',    hex: '#2F80ED' },
    { nome: 'accent-green',   hex: '#54C571' },
    { nome: 'danger',         hex: '#E25A52' },
    { nome: 'accent-purple',  hex: '#8B6FE8' },
    { nome: 'accent-orange',  hex: '#E89B3C' },
  ];
</script>

<div class="color-palette">
  {#each CORES as cor}
    <button
      type="button"
      class="swatch"
      class:selected={value?.toLowerCase() === cor.hex.toLowerCase()}
      style="background:{cor.hex}"
      title="{cor.nome} · {cor.hex}"
      on:click={() => value = cor.hex}
    ></button>
  {/each}
</div>

<style>
.color-palette { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.swatch {
  width: 18px; height: 18px; border-radius: 4px;
  border: 1px solid var(--border); cursor: pointer; padding: 0;
}
.swatch.selected { outline: 2px solid var(--accent-blue); outline-offset: 1px; }
</style>
