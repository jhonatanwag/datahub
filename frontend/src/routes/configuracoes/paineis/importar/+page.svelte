<script>
  import { api } from '$lib/api.js';

  let bundle = null;
  let plano = null;
  let avisos = [];
  let erro = null;
  let carregando = false;
  let resultado = null;

  // seleção: chave = "tipo:slug" ou "painel"
  let marcados = {};

  async function aoEscolherArquivo(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    erro = null; plano = null; resultado = null;
    try {
      const texto = await file.text();
      bundle = JSON.parse(texto);
    } catch {
      erro = 'Arquivo inválido: não é um JSON.';
      return;
    }
    carregando = true;
    try {
      const r = await api.analisarImportPainel(bundle);
      plano = r.plano;
      avisos = r.avisos || [];
      marcados = {};
      const pre = (item, chave) => { marcados[chave] = item.situacao !== 'identico'; };
      pre(plano.painel, 'painel');
      for (const q of plano.queries) pre(q, `queries:${q.slug}`);
      for (const v of plano.variaveis) pre(v, `variaveis:${v.slug}`);
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  async function aplicar() {
    erro = null; resultado = null;
    const aplicarPayload = {
      painel: !!marcados['painel'],
      queries: plano.queries.filter(q => marcados[`queries:${q.slug}`]).map(q => q.slug),
      variaveis: plano.variaveis.filter(v => marcados[`variaveis:${v.slug}`]).map(v => v.slug),
    };
    carregando = true;
    try {
      resultado = await api.importarPainel({ bundle, aplicar: aplicarPayload });
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  const cor = (s) => s === 'novo' ? 'novo' : s === 'conflito' ? 'conflito' : 'identico';
  const rotulo = (s) => s === 'novo' ? 'novo' : s === 'conflito' ? 'conflito' : 'idêntico';
</script>

<svelte:head><title>Importar painel — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Importar painel</h2>
    <a href="/configuracoes/paineis" class="btn-ghost">Voltar</a>
  </div>

  <input type="file" accept="application/json,.json" on:change={aoEscolherArquivo} />

  {#if carregando}<p class="muted">Processando…</p>{/if}
  {#if erro}<p class="error">{erro}</p>{/if}

  {#if avisos.length}
    <div class="avisos">
      <strong>Avisos:</strong>
      <ul>{#each avisos as a}<li>{a}</li>{/each}</ul>
    </div>
  {/if}

  {#if resultado}
    <div class="ok">
      Importado. Aplicado: {resultado.aplicado.variaveis} variáveis,
      {resultado.aplicado.queries} queries{resultado.aplicado.painel ? ', painel' : ''}.
      <a href="/configuracoes/paineis">Ver painéis</a>
    </div>
  {/if}

  {#if plano && !resultado}
    <table class="plano">
      <thead><tr><th></th><th>Tipo</th><th>Slug</th><th>Nome</th><th>Situação</th><th>Campos diferentes</th></tr></thead>
      <tbody>
        <tr>
          <td><input type="checkbox" bind:checked={marcados['painel']} disabled={plano.painel.situacao === 'identico'} /></td>
          <td>painel</td>
          <td><code>{plano.painel.slug}</code></td>
          <td>{plano.painel.nome}</td>
          <td><span class="badge {cor(plano.painel.situacao)}">{rotulo(plano.painel.situacao)}</span></td>
          <td class="muted">{plano.painel.campos_diferentes.join(', ')}</td>
        </tr>
        {#each plano.queries as q}
          <tr>
            <td><input type="checkbox" bind:checked={marcados[`queries:${q.slug}`]} disabled={q.situacao === 'identico'} /></td>
            <td>query</td>
            <td><code>{q.slug}</code></td>
            <td>{q.nome}</td>
            <td><span class="badge {cor(q.situacao)}">{rotulo(q.situacao)}</span></td>
            <td class="muted">{q.campos_diferentes.join(', ')}</td>
          </tr>
        {/each}
        {#each plano.variaveis as v}
          <tr>
            <td><input type="checkbox" bind:checked={marcados[`variaveis:${v.slug}`]} disabled={v.situacao === 'identico'} /></td>
            <td>variável</td>
            <td><code>{v.slug}</code></td>
            <td>{v.nome}</td>
            <td><span class="badge {cor(v.situacao)}">{rotulo(v.situacao)}</span></td>
            <td class="muted">{v.campos_diferentes.join(', ')}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <button class="btn-primary" on:click={aplicar} disabled={carregando}>Aplicar</button>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.muted { color: var(--muted); font-size: 12px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.avisos { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin: 16px 0; font-size: 13px; }
.avisos ul { margin: 6px 0 0 18px; }
.ok { background: #1a4731; color: #3fb950; border-radius: 6px; padding: 12px; margin: 16px 0; font-size: 13px; }
.plano { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
.plano th, .plano td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
.plano code { color: var(--accent-blue); font-family: var(--font-display); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.badge.novo { background: #1a4731; color: #3fb950; }
.badge.conflito { background: #4d3800; color: #d29922; }
.badge.identico { background: var(--surface2); color: var(--muted); }
</style>
