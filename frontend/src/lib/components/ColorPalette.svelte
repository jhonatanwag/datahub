<script>
  export let value = '';

  // Paleta de referência do tema (noite e dia) do app.css — fixa, não reage ao
  // tema do usuário logado, já que a cor do KPI é um hex estático salvo por query.
  // Obs.: #161b22 / #2B5A45 (padrão antigo) e o fundo/fonte padrão fazem o KPI seguir o tema.
  const CORES = [
    { nome: 'noite · fundo',    hex: '#0E131C' },
    { nome: 'noite · cartão',   hex: '#161E2C' },
    { nome: 'noite · borda',    hex: '#263146' },
    { nome: 'noite · texto',    hex: '#E7ECF4' },
    { nome: 'dia · fundo',      hex: '#F3F6FA' },
    { nome: 'dia · cartão',     hex: '#FFFFFF' },
    { nome: 'dia · borda',      hex: '#E1E8F0' },
    { nome: 'dia · texto',      hex: '#1B2634' },
    { nome: 'muted',            hex: '#8C99AF' },
    { nome: 'destaque (noite)', hex: '#3FCF9F' },
    { nome: 'destaque (dia)',   hex: '#1FA97C' },
    { nome: 'azul',             hex: '#6C8CFF' },
    { nome: 'roxo',             hex: '#A58BFF' },
    { nome: 'âmbar',            hex: '#F2B35B' },
    { nome: 'perigo',           hex: '#F26D6D' },
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
