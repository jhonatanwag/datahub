<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import { ordenarLista, proximaDirecao } from '$lib/sort.js';

  let queries     = [];
  let filtroTipo  = '';
  let loading     = true;
  let erro        = null;
  let ordenarCampo   = null;
  let ordenarDirecao = null;

  const tipos = [
    { value: '',                     label: 'Todos' },
    { value: 'kpi',                  label: 'KPI' },
    { value: 'chart_line',           label: 'Gráfico Linha' },
    { value: 'chart_bar',            label: 'Gráfico Barra' },
    { value: 'chart_bar_horizontal', label: 'Barra Horizontal' },
    { value: 'chart_doughnut',       label: 'Rosca' },
    { value: 'table',                label: 'Tabela' },
    { value: 'rag_context',          label: 'Contexto IA' },
  ];

  const colunas = [
    { label: 'Slug',      campo: 'slug' },
    { label: 'Nome',      campo: 'nome' },
    { label: 'Tipo',      campo: 'tipo' },
    { label: 'Cache TTL', campo: 'cache_ttl' },
    { label: 'Escopo',    campo: 'empresa_id' },
    { label: 'Ativo',     campo: 'ativo' },
    { label: 'Ações',     campo: null },
  ];

  function onClickColuna(campo) {
    if (!campo) return;
    ordenarDirecao = proximaDirecao(campo, ordenarCampo, ordenarDirecao);
    ordenarCampo = ordenarDirecao ? campo : null;
  }

  onMount(async () => {
    try {
      queries = await api.listarQueries();
    } catch (e) {
      erro = e.message;
    } finally {
      loading = false;
    }
  });

  $: filtradas = filtroTipo ? queries.filter(q => q.tipo === filtroTipo) : queries;
  $: ordenadas = ordenarLista(filtradas, ordenarCampo, ordenarDirecao);

  async function toggleAtivo(q) {
    const original = q.ativo;
    q.ativo = !q.ativo;
    queries = queries;
    try {
      await api.atualizarQuery(q.id, { ativo: q.ativo });
    } catch (e) {
      q.ativo = original;
      queries = queries;
      alert('Erro ao atualizar: ' + e.message);
    }
  }

  async function deletar(q) {
    if (!confirm(`Deletar "${q.nome}"?`)) return;
    try {
      await api.deletarQuery(q.id);
      queries = queries.filter(x => x.id !== q.id);
    } catch (e) {
      alert('Erro ao deletar: ' + e.message);
    }
  }
</script>

<svelte:head><title>Queries — DataHub</title></svelte:head>

<div style="padding:24px;">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
    <h2 style="font-family:var(--font-display)">Queries do Dashboard</h2>
    <a href="/configuracoes/queries/nova" class="btn-primary" style="display:inline-block; padding:8px 16px; border-radius:6px; color:#0d1117; background:var(--accent); font-weight:600; text-decoration:none">Nova Query</a>
  </div>

  <div style="margin-bottom:16px;">
    <select bind:value={filtroTipo} style="width:200px;">
      {#each tipos as t}<option value={t.value}>{t.label}</option>{/each}
    </select>
  </div>

  {#if loading}
    <p style="color:var(--muted)">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <div class="card" style="padding:0; overflow:hidden;">
      <table style="width:100%; border-collapse:collapse;">
        <thead>
          <tr>
            {#each colunas as c}
              <th
                style="padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); font-size:11px; text-transform:uppercase; color:var(--muted); {c.campo ? 'cursor:pointer' : ''}"
                on:click={() => onClickColuna(c.campo)}
              >
                {c.label}{#if ordenarCampo === c.campo}{ordenarDirecao === 'asc' ? ' ▲' : ' ▼'}{/if}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each ordenadas as q}
            <tr>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); font-family:var(--font-display); font-size:12px;">{q.slug}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border);">{q.nome}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--accent-blue); font-size:12px;">{q.tipo}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--muted);">{q.cache_ttl}s</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--muted);">{q.empresa_id ? `Empresa #${q.empresa_id}` : 'Global'}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border);">
                <button class="btn-ghost" style="padding:4px 10px; font-size:12px;" on:click={() => toggleAtivo(q)}>
                  {q.ativo ? '✓ Ativo' : '✗ Inativo'}
                </button>
              </td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); display:flex; gap:6px;">
                <a href="/configuracoes/queries/{q.id}" class="btn-ghost" style="padding:4px 10px; font-size:12px;">Editar</a>
                <button class="btn-ghost" style="padding:4px 10px; font-size:12px; color:var(--accent);" on:click={() => deletar(q)}>Deletar</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
