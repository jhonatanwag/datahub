<script>
  import GrupoLinha from './GrupoLinha.svelte';
  import Modal from './Modal.svelte';
  import DataTable from './DataTable.svelte';
  import KPICard from './KPICard.svelte';
  import ChartPanel from './ChartPanel.svelte';
  import MapPanel from './MapPanel.svelte';
  import { api } from '$lib/api.js';

  export let colunas = [];
  export let dados = [];
  export let agrupamentos = [];
  export let agregacoes = [];
  export let subquery = null;
  export let titulo = 'dados';

  const FUNCOES = {
    soma:     vals => vals.reduce((a, b) => a + b, 0),
    contagem: vals => vals.length,
    media:    vals => vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
    minimo:   vals => vals.length ? Math.min(...vals) : 0,
    maximo:   vals => vals.length ? Math.max(...vals) : 0,
  };

  function calcularAgregacoes(linhas, agregacoesAtual) {
    return agregacoesAtual.map(ag => {
      const valores = linhas.map(r => Number(r[ag.coluna])).filter(v => !Number.isNaN(v));
      return { coluna: ag.coluna, label: ag.label, valor: (FUNCOES[ag.funcao] ?? FUNCOES.soma)(valores) };
    });
  }

  function construirArvore(linhas, nivel, agrupamentosAtual, agregacoesAtual) {
    if (nivel >= agrupamentosAtual.length) return { folha: true, linhas };
    const coluna = agrupamentosAtual[nivel];
    const grupos = new Map();
    for (const linha of linhas) {
      const chave = linha[coluna];
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(linha);
    }
    return {
      folha: false,
      grupos: [...grupos.entries()].map(([valor, linhasGrupo]) => ({
        valor,
        agregados: calcularAgregacoes(linhasGrupo, agregacoesAtual),
        filho: construirArvore(linhasGrupo, nivel + 1, agrupamentosAtual, agregacoesAtual),
      })),
    };
  }

  $: colunasDetalhe = (colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
  ).filter(c => !agrupamentos.includes(c.key));

  $: arvore = construirArvore(dados, 0, agrupamentos, agregacoes);
  $: mostrarAcoes = !!subquery;

  let modalAberto     = false;
  let modalCarregando = false;
  let modalErro       = null;
  let modalDados      = null;

  async function acionar(row) {
    if (!subquery) return;
    modalAberto     = true;
    modalCarregando = true;
    modalErro       = null;
    modalDados      = null;
    try {
      const params = Object.fromEntries(
        subquery.parametros.map(m => [m.parametro_destino, row[m.coluna_origem]])
      );
      const res = await api.executarQuery(subquery.slug, params);
      modalDados = res.data;
    } catch (e) {
      modalErro = e.message;
    } finally {
      modalCarregando = false;
    }
  }
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunasDetalhe as col}<th>{col.label ?? col.key}</th>{/each}
        {#each agregacoes as ag}<th class="agregado-header">{ag.label ?? ag.coluna}</th>{/each}
        {#if mostrarAcoes}<th>Ações</th>{/if}
      </tr>
    </thead>
    <tbody>
      <GrupoLinha no={arvore} {colunasDetalhe} {agregacoes} {mostrarAcoes} onAcionar={acionar} nivel={0} />
    </tbody>
  </table>
</div>

<Modal aberto={modalAberto} onClose={() => modalAberto = false}>
  {#if modalCarregando}
    <p>Carregando...</p>
  {:else if modalErro}
    <p class="error">{modalErro}</p>
  {:else if subquery?.tipo === 'kpi'}
    <KPICard dados={modalDados?.[0]} />
  {:else if subquery?.tipo?.startsWith('chart_')}
    <ChartPanel tipo={subquery.tipo} dados={modalDados ?? []} />
  {:else if subquery?.tipo === 'map'}
    <MapPanel pontos={modalDados ?? []} />
  {:else}
    <DataTable dados={modalDados ?? []} titulo={titulo} />
  {/if}
</Modal>

<style>
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.error { color: var(--danger, #f85149); }
</style>
