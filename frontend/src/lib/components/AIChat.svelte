<script>
  import { api } from '$lib/api.js';

  let input = '';
  let historico = [];
  let carregando = false;

  async function enviar() {
    if (!input.trim() || carregando) return;
    const pergunta = input.trim();
    input = '';
    historico = [...historico, { tipo: 'user', texto: pergunta }];
    carregando = true;
    try {
      const res = await api.perguntarIA(pergunta);
      historico = [...historico, { tipo: 'ai', texto: res.resposta }];
    } catch (e) {
      historico = [...historico, { tipo: 'error', texto: 'Erro ao obter resposta.' }];
    } finally {
      carregando = false;
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
  }
</script>

<div class="chat">
  <div class="messages">
    {#each historico as msg}
      <div class="msg msg--{msg.tipo}">
        <span class="origin">{msg.tipo === 'user' ? 'Você' : msg.tipo === 'ai' ? 'IA' : '!'}</span>
        <p>{msg.texto}</p>
      </div>
    {/each}
    {#if carregando}
      <div class="msg msg--ai loading">
        <span class="origin">IA</span>
        <p>Analisando dados<span class="dots">...</span></p>
      </div>
    {/if}
  </div>

  <div class="input-row">
    <textarea
      bind:value={input}
      on:keydown={onKeydown}
      placeholder="Pergunte sobre os dados da empresa..."
      rows="2"
      disabled={carregando}
    ></textarea>
    <button class="btn-primary" on:click={enviar} disabled={carregando || !input.trim()}>
      Enviar
    </button>
  </div>
</div>

<style>
.chat { display: flex; flex-direction: column; height: 100%; gap: 16px; }
.messages { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; max-height: 400px; padding-right: 4px; }
.msg { padding: 12px 16px; border-radius: var(--radius); max-width: 85%; }
.msg--user  { background: var(--surface2); align-self: flex-end; }
.msg--ai    { background: var(--surface); border: 1px solid var(--border); align-self: flex-start; }
.msg--error { background: rgba(247,129,102,.1); border: 1px solid var(--accent); align-self: flex-start; }
.origin { display: block; font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row textarea { resize: none; }
@keyframes blink { 50% { opacity: 0; } }
.dots { animation: blink 1s infinite; }
</style>
