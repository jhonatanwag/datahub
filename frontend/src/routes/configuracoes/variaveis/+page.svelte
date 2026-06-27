<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let variaveis   = [];
  let carregando  = true;
  let erro        = null;

  onMount(async () => {
    try {
      variaveis = await api.listarVariaveis();
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  async function desativar(v) {
    if (!confirm(`Desativar "${v.nome}"?`)) return;
    try {
      await api.desativarVariavel(v.id);
      variaveis = variaveis.filter(x => x.id !== v.id);
    } catch (e) {
      alert(e.message);
    }
  }

  const tipoLabel = {
    date: 'Data', date_range: 'Intervalo de datas',
    select: 'Seleção', multiselect: 'Multi-seleção',
    text: 'Texto', number: 'Número'
  };
</script>

<svelte:head><title>Variáveis — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Variáveis de Filtro</h2>
    <a href="/configuracoes/variaveis/nova" class="btn-primary">+ Nova Variável</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if variaveis.length === 0}
    <p class="muted">Nenhuma variável cadastrada.</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Slug</th>
          <th>Nome</th>
          <th>Tipo</th>
          <th>Parâmetros</th>
          <th>Query Fonte</th>
          <th>Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each variaveis as v}
          <tr>
            <td class="mono">{v.slug}</td>
            <td>{v.nome}</td>
            <td><span class="badge">{tipoLabel[v.tipo] || v.tipo}</span></td>
            <td class="mono small">{v.param_names?.join(', ') || '—'}</td>
            <td class="small">{v.query_fonte ? '✓ Sim' : '—'}</td>
            <td class="actions-cell">
              <a href="/configuracoes/variaveis/{v.id}" class="btn-ghost btn-sm">Editar</a>
              <button class="btn-ghost btn-sm danger" on:click={() => desativar(v)}>Desativar</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--muted); border-bottom: 1px solid var(--border); font-weight: 500; }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
.mono { font-family: var(--font-display); font-size: 12px; }
.small { font-size: 12px; color: var(--muted); }
.actions-cell { display: flex; gap: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
