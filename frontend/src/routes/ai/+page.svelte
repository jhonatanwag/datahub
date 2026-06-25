<script>
  import { onMount } from 'svelte';
  import AIChat from '$lib/components/AIChat.svelte';
  import { api } from '$lib/api.js';

  let historico = [];

  onMount(async () => {
    try {
      historico = await api.historicoIA();
    } catch {}
  });
</script>

<svelte:head><title>IA / Chat — DataHub</title></svelte:head>

<div style="padding:24px; max-width:800px; margin:0 auto;">
  <h2 style="margin-bottom:20px; font-family:var(--font-display); color:var(--accent-blue)">Assistente de Analytics</h2>

  {#if historico.length > 0}
    <details class="card" style="margin-bottom:16px;">
      <summary style="cursor:pointer; color:var(--muted); font-size:13px">
        Histórico de conversas ({historico.length})
      </summary>
      <div style="margin-top:12px; display:flex; flex-direction:column; gap:10px;">
        {#each historico as item}
          <div style="border-left:2px solid var(--border); padding-left:12px;">
            <p style="font-size:12px; color:var(--muted)">{item.criado_em}</p>
            <p style="font-weight:500">↑ {item.pergunta}</p>
            <p style="color:var(--muted); font-size:13px">↓ {item.resposta}</p>
          </div>
        {/each}
      </div>
    </details>
  {/if}

  <div class="card">
    <AIChat />
  </div>
</div>
