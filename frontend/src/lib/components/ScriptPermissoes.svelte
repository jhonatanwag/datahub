<script>
  import { onMount } from 'svelte';

  // carregar: () => Promise<{ script: string }>
  export let carregar;
  export let titulo = 'Script de permissões (PSOEDUCARE)';

  let script = '';
  let erro = null;
  let carregando = true;
  let copiado = false;

  async function buscar() {
    carregando = true;
    erro = null;
    try {
      script = (await carregar()).script;
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(script);
    } catch {
      const el = document.getElementById('script-permissoes-txt');
      el?.select();
      document.execCommand('copy');
    }
    copiado = true;
    setTimeout(() => (copiado = false), 2000);
  }

  onMount(buscar);
</script>

<div class="script-box">
  <div class="head">
    <h3>{titulo}</h3>
    <div class="btns">
      <button class="btn-ghost" on:click={buscar} disabled={carregando}>Atualizar</button>
      <button class="btn-primary" on:click={copiar} disabled={carregando || !script}>
        {copiado ? 'Copiado ✓' : 'Copiar'}
      </button>
    </div>
  </div>
  <p class="hint">Execute no banco do PSOEDUCARE. Pode rodar mais de uma vez: registros existentes são ignorados.</p>
  {#if erro}
    <p class="err">{erro}</p>
  {:else}
    <textarea id="script-permissoes-txt" readonly rows="16" value={carregando ? 'Carregando...' : script}></textarea>
  {/if}
</div>

<style>
.script-box { display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h3 { font-size: 15px; color: var(--text); margin: 0; }
.btns { display: flex; gap: 8px; }
.hint { font-size: 12px; color: var(--muted); margin: 0; }
.err { color: #f85149; font-size: 13px; }
textarea { font-family: monospace; font-size: 12px; padding: 8px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); color: var(--text); resize: vertical; width: 100%; box-sizing: border-box; white-space: pre; }
</style>
