<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import QueryEditor from '$lib/components/QueryEditor.svelte';

  let form = {
    slug: '', nome: '', descricao: '',
    sql_texto: '', tipo: 'kpi',
    empresa_id: null, cache_ttl: 300, ativo: true
  };

  let testando      = false;
  let resultadoTeste = null;
  let salvando      = false;
  let erro          = null;

  const tipos = [
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context'
  ];

  async function testar(sql) {
    testando = true;
    try {
      resultadoTeste = await api.testarQuery({ ...form, sql_texto: sql });
    } catch (e) {
      resultadoTeste = { ok: false, erro: e.message };
    } finally {
      testando = false;
    }
    return resultadoTeste;
  }

  async function salvar() {
    if (!resultadoTeste?.ok) {
      erro = 'Teste a query antes de salvar.';
      return;
    }
    erro = null;
    salvando = true;
    try {
      await api.criarQuery(form);
      goto('/configuracoes/queries');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Query — DataHub</title></svelte:head>

<div style="padding:24px; max-width:800px; margin:0 auto;">
  <div style="display:flex; align-items:center; gap:16px; margin-bottom:24px;">
    <a href="/configuracoes/queries" style="color:var(--muted)">← Voltar</a>
    <h2 style="font-family:var(--font-display)">Nova Query</h2>
  </div>

  <div class="card" style="display:flex; flex-direction:column; gap:16px;">
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
      <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
        Slug (identificador único)
        <input bind:value={form.slug} placeholder="ex: kpi_receita" />
      </label>
      <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
        Nome legível
        <input bind:value={form.nome} placeholder="ex: Receita Total (30d)" />
      </label>
    </div>

    <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
      Tipo
      <select bind:value={form.tipo}>
        {#each tipos as t}<option value={t}>{t}</option>{/each}
      </select>
    </label>

    <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
      Cache TTL (segundos, 0 = sem cache)
      <input type="number" bind:value={form.cache_ttl} min="0" />
    </label>

    <div style="border-top:1px solid var(--border); padding-top:16px;">
      <p style="font-size:13px; color:var(--muted); margin-bottom:10px;">SQL da Query</p>
      <QueryEditor
        bind:sql={form.sql_texto}
        tipo={form.tipo}
        onTestar={testar}
      />
    </div>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={salvar} disabled={salvando || !resultadoTeste?.ok}>
      {salvando ? 'Salvando...' : 'Salvar Query'}
    </button>
  </div>
</div>
