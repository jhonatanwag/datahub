<script>
  import { onMount, onDestroy } from 'svelte';
  import { api } from '$lib/api.js';

  let input = '';
  let historico = [];
  let carregando = false;
  let gravando = false;
  let transcrevendo = false;
  let erroMic = null;
  let suportaGravacao = false;
  let mediaRecorder = null;
  let audioChunks = [];
  let tokensRestantes = null;
  let tokensLimite = null;
  let esperaSegundos = 0;
  let esperaTimer = null;

  onMount(() => {
    suportaGravacao = typeof navigator !== 'undefined'
      && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
      && typeof MediaRecorder !== 'undefined';
  });

  onDestroy(() => {
    if (esperaTimer) clearInterval(esperaTimer);
  });

  function iniciarEspera(segundos) {
    esperaSegundos = segundos;
    if (esperaTimer) clearInterval(esperaTimer);
    esperaTimer = setInterval(() => {
      esperaSegundos -= 1;
      if (esperaSegundos <= 0) {
        clearInterval(esperaTimer);
        esperaTimer = null;
        esperaSegundos = 0;
      }
    }, 1000);
  }

  async function enviar() {
    if (!input.trim() || carregando || esperaSegundos > 0) return;
    const pergunta = input.trim();
    input = '';
    historico = [...historico, { tipo: 'user', texto: pergunta }];
    carregando = true;
    try {
      const res = await api.perguntarIA(pergunta);
      historico = [...historico, { tipo: 'ai', texto: res.resposta }];
      if (res.tokens_restantes != null) tokensRestantes = res.tokens_restantes;
      if (res.tokens_limite != null) tokensLimite = res.tokens_limite;
    } catch (e) {
      if (e.espereSegundos) {
        historico = [...historico, { tipo: 'error', texto: `⏳ Limite de uso da IA atingido. Aguarde ${e.espereSegundos}s antes de perguntar de novo.` }];
        iniciarEspera(e.espereSegundos);
      } else {
        historico = [...historico, { tipo: 'error', texto: e.message || 'Erro ao obter resposta.' }];
      }
    } finally {
      carregando = false;
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
  }

  async function alternarGravacao() {
    if (gravando) {
      mediaRecorder?.stop();
      return;
    }
    erroMic = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        gravando = false;
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        await transcreverEEnviar(blob);
      };
      mediaRecorder.start();
      gravando = true;
    } catch (e) {
      erroMic = 'Não foi possível acessar o microfone.';
    }
  }

  async function transcreverEEnviar(blob) {
    transcrevendo = true;
    try {
      const res = await api.transcreverAudio(blob);
      const texto = (res.texto || '').trim();
      if (texto) {
        input = texto;
        await enviar();
      } else {
        erroMic = 'Não entendi o áudio — tenta de novo.';
      }
    } catch (e) {
      erroMic = 'Erro ao transcrever o áudio.';
    } finally {
      transcrevendo = false;
    }
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
    {#if transcrevendo}
      <div class="msg msg--user loading">
        <span class="origin">Você</span>
        <p>Transcrevendo áudio<span class="dots">...</span></p>
      </div>
    {/if}
    {#if carregando}
      <div class="msg msg--ai loading">
        <span class="origin">IA</span>
        <p>Analisando dados<span class="dots">...</span></p>
      </div>
    {/if}
  </div>

  {#if erroMic}
    <p class="erro-mic">{erroMic}</p>
  {/if}

  {#if esperaSegundos > 0}
    <p class="aviso-limite">⏳ Limite de uso da IA atingido — aguarde {esperaSegundos}s pra perguntar de novo.</p>
  {/if}

  <div class="input-row">
    <textarea
      bind:value={input}
      on:keydown={onKeydown}
      placeholder="Pergunte sobre os dados da empresa..."
      rows="2"
      disabled={carregando || gravando || transcrevendo || esperaSegundos > 0}
    ></textarea>

    {#if suportaGravacao}
      <button
        class="btn-mic"
        class:gravando
        on:click={alternarGravacao}
        disabled={carregando || transcrevendo || esperaSegundos > 0}
        title={gravando ? 'Parar gravação' : 'Gravar pergunta por voz'}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" x2="12" y1="19" y2="22"/>
        </svg>
      </button>
    {/if}

    <button class="btn-primary" on:click={enviar} disabled={carregando || gravando || transcrevendo || esperaSegundos > 0 || !input.trim()}>
      {esperaSegundos > 0 ? `Aguarde ${esperaSegundos}s` : 'Enviar'}
    </button>
  </div>

  {#if tokensLimite != null}
    <p class="contador-tokens">Uso da IA: {tokensRestantes?.toLocaleString('pt-BR')} / {tokensLimite?.toLocaleString('pt-BR')} tokens disponíveis (por minuto)</p>
  {/if}
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
.erro-mic { color: var(--accent); font-size: 12px; margin: 0; }
.aviso-limite { color: var(--accent); font-size: 13px; margin: 0; font-weight: 500; }
.contador-tokens { color: var(--muted); font-size: 11px; margin: 0; text-align: right; }
.btn-mic {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--muted);
  cursor: pointer;
}
.btn-mic:hover:not(:disabled) { color: var(--accent-blue); border-color: var(--accent-blue); }
.btn-mic:disabled { opacity: .5; cursor: default; }
.btn-mic.gravando { color: var(--accent); border-color: var(--accent); animation: pulse 1s infinite; }
@keyframes pulse { 50% { opacity: .5; } }
@keyframes blink { 50% { opacity: 0; } }
.dots { animation: blink 1s infinite; }
</style>
