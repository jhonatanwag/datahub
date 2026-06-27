<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let form = {
    slug: '', nome: '', descricao: '',
    tipo: 'date', query_fonte: '', param_names: [], ativo: true
  };

  let testando       = false;
  let resultadoTeste = null;
  let salvando       = false;
  let erro           = null;

  const tipos = [
    { value: 'date',        label: 'Data única' },
    { value: 'date_range',  label: 'Intervalo de datas' },
    { value: 'select',      label: 'Seleção (dropdown)' },
    { value: 'multiselect', label: 'Multi-seleção' },
    { value: 'text',        label: 'Texto livre' },
    { value: 'number',      label: 'Número' },
  ];

  const paramsPorTipo = {
    date:        ['data'],
    date_range:  ['data_inicio', 'data_fim'],
    select:      [],
    multiselect: [],
    text:        [],
    number:      [],
  };

  $: {
    const base = paramsPorTipo[form.tipo] || [];
    if (base.length > 0) {
      form.param_names = base;
    } else if (form.slug) {
      form.param_names = [form.slug];
    }
  }

  $: needsQuery = form.tipo === 'select' || form.tipo === 'multiselect';

  function gerarSlug(nome) {
    return nome.toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  }

  async function testarFonte() {
    if (!form.query_fonte) return;
    testando = true;
    resultadoTeste = null;
    const slugTemp = form.slug || `_temp_${Date.now()}`;
    let criadaId = null;
    try {
      const criada = await api.criarVariavel({ ...form, slug: slugTemp });
      criadaId = criada.id;
      const resultado = await api.executarFonteVariavel(criadaId);
      resultadoTeste = { ok: true, linhas: resultado.length, amostra: resultado.slice(0, 5) };
    } catch (e) {
      resultadoTeste = { ok: false, erro: e.message };
    } finally {
      if (criadaId) await api.desativarVariavel(criadaId).catch(() => {});
      testando = false;
    }
  }

  async function salvar() {
    if (!form.nome) { erro = 'Nome é obrigatório.'; return; }
    if (!form.slug) { form.slug = gerarSlug(form.nome); }
    if (needsQuery && !form.query_fonte) { erro = 'Query fonte é obrigatória para este tipo.'; return; }
    erro = null;
    salvando = true;
    try {
      await api.criarVariavel(form);
      goto('/configuracoes/variaveis');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Variável — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <a href="/configuracoes/variaveis" class="back-link">← Voltar</a>
    <h2>Nova Variável de Filtro</h2>
  </div>

  <div class="form-card">
    <div class="field">
      <label>Nome</label>
      <input
        type="text"
        bind:value={form.nome}
        placeholder="ex: Período"
        on:input={() => { if (!form.slug) form.slug = gerarSlug(form.nome); }}
      />
    </div>

    <div class="field">
      <label>Slug</label>
      <input type="text" bind:value={form.slug} placeholder="ex: periodo" />
    </div>

    <div class="field">
      <label>Tipo</label>
      <select bind:value={form.tipo}>
        {#each tipos as t}
          <option value={t.value}>{t.label}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <label>Parâmetros gerados</label>
      <input type="text" value={form.param_names.join(', ')} readonly class="readonly" />
      <span class="hint">Preenchido automaticamente pelo tipo</span>
    </div>

    <div class="field">
      <label>Descrição</label>
      <input type="text" bind:value={form.descricao} placeholder="Descrição opcional" />
    </div>

    {#if needsQuery}
      <div class="field">
        <label>Query Fonte (SQL)</label>
        <span class="hint">Deve retornar colunas <code>valor</code> e <code>label</code></span>
        <textarea
          bind:value={form.query_fonte}
          rows="5"
          placeholder="SELECT id AS valor, nome AS label FROM tabela ORDER BY nome"
        ></textarea>
        <button class="btn-ghost" on:click={testarFonte} disabled={testando}>
          {testando ? 'Testando...' : 'Testar Query'}
        </button>

        {#if resultadoTeste}
          {#if resultadoTeste.ok}
            <div class="teste-ok">
              ✓ {resultadoTeste.linhas} opções encontradas.
              {#if resultadoTeste.amostra?.length}
                <table class="amostra-table">
                  <thead><tr><th>valor</th><th>label</th></tr></thead>
                  <tbody>
                    {#each resultadoTeste.amostra as row}
                      <tr><td>{row.valor}</td><td>{row.label}</td></tr>
                    {/each}
                  </tbody>
                </table>
              {/if}
            </div>
          {:else}
            <p class="error">{resultadoTeste.erro}</p>
          {/if}
        {/if}
      </div>
    {/if}

    {#if erro}
      <p class="error">{erro}</p>
    {/if}

    <div class="actions">
      <a href="/configuracoes/variaveis" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" on:click={salvar} disabled={salvando}>
        {salvando ? 'Salvando...' : 'Salvar Variável'}
      </button>
    </div>
  </div>
</div>

<style>
.page { padding: 24px; max-width: 640px; }
.page-header { margin-bottom: 24px; }
.back-link { color: var(--muted); font-size: 13px; display: block; margin-bottom: 8px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
label { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
input, select, textarea { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; }
textarea { resize: vertical; font-family: var(--font-display); }
.readonly { opacity: .6; cursor: default; }
.hint { font-size: 11px; color: var(--muted); }
.actions { display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.teste-ok { font-size: 12px; color: #3fb950; }
.amostra-table { margin-top: 8px; border-collapse: collapse; font-size: 12px; }
.amostra-table th, .amostra-table td { border: 1px solid var(--border); padding: 4px 8px; color: var(--text); }
</style>
