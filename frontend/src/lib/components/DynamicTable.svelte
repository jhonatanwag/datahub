<script>
  import GrupoLinha from './GrupoLinha.svelte';
  import Modal from './Modal.svelte';
  import DataTable from './DataTable.svelte';
  import KPICard from './KPICard.svelte';
  import ChartPanel from './ChartPanel.svelte';
  import MapPanel from './MapPanel.svelte';
  import { api } from '$lib/api.js';
  import { baixarCSVAgrupado, baixarXLSXAgrupado } from '$lib/exportTable.js';
  import { construirArvore, montarPivot } from '$lib/tabelaDinamica.js';
  import {
    excedeLimiteRelatorio, textoAvisoLimite, excedeColunasPivotRelatorio, textoAvisoColunasPivot,
  } from '$lib/relatorioLimites.js';
  import { abrirPdf, compartilharWhatsapp, podeCompartilhar } from '$lib/relatorioPdf.js';

  export let colunas = [];
  export let dados = [];
  export let agrupamentos = [];
  export let agregacoes = [];
  export let pivot = null;          // { coluna, ordem_coluna, total } — colunas dinâmicas (ex.: meses)
  export let subquery = null;
  export let titulo = 'dados';
  export let modoRelatorio = false;
  export let painelSlug   = null;   // usados só fora do modo relatório (Task 6)
  export let indicadorId  = null;
  export let filtrosQuery = '';

  $: colunasTodas = colunas.length > 0
    ? colunas
    : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : []);

  // Pivô só faz sentido com ao menos um agrupamento (as células ficam nas linhas de grupo).
  $: pivotCtx = agrupamentos.length ? montarPivot(dados, pivot, agregacoes) : null;

  // A coluna que só ordena o pivô (ex.: yyyymm) não deve aparecer nas linhas de detalhe.
  $: colunasDetalhe = colunasTodas.filter(
    c => !agrupamentos.includes(c.key) && c.key !== pivotCtx?.ordemColuna
  );

  // No pivô, as colunas da direita são as do pivô (uma por valor + Total Geral)
  // em vez das agregações; mesma forma ({label}) então cabeçalho/export/padding servem igual.
  $: agregacoesEfetivas = pivotCtx ? pivotCtx.cabecalhos : agregacoes;

  $: arvore = construirArvore(dados, 0, agrupamentos, agregacoes, pivotCtx);
  $: mostrarAcoes = !!subquery;

  // Relatório grande: mantém grupos/totais (calculados sobre TODOS os dados, então corretos)
  // e omite as linhas de detalhe — é o detalhe que multiplica o DOM. Ver relatorioLimites.js.
  $: ocultarDetalhe = modoRelatorio && excedeLimiteRelatorio(dados.length);

  // Pivô com colunas demais não cabe na página: no relatório nem monta a tabela (só o aviso).
  $: pivotLargoDemais = modoRelatorio && !!pivotCtx && excedeColunasPivotRelatorio(pivotCtx.valores.length);

  // Grupos começam todos recolhidos — só as linhas de agrupamento aparecem
  // até o usuário clicar pra expandir. Chave = caminho dos valores dos
  // grupos ancestrais, então o estado sobrevive a um recálculo da árvore
  // (novo filtro/dado) desde que os valores dos grupos não mudem.
  let expandidos = new Set();
  function alternar(chave) {
    if (expandidos.has(chave)) expandidos.delete(chave);
    else expandidos.add(chave);
    expandidos = expandidos;
  }

  // No relatório a árvore sai toda expandida — um "Set" que responde sempre true.
  $: expandidosEfetivo = modoRelatorio ? { has: () => true } : expandidos;

  let gerandoPdf = false;
  const compartilhavel = podeCompartilhar();

  async function exportarPDF() {
    if (!painelSlug || indicadorId == null) return;
    gerandoPdf = true;
    try { await abrirPdf(painelSlug, { indicador: indicadorId, filtrosQuery }); }
    catch (e) { alert('Erro ao gerar o PDF: ' + e.message); }
    finally { gerandoPdf = false; }
  }

  async function enviarWhatsapp() {
    if (!painelSlug || indicadorId == null) return;
    gerandoPdf = true;
    try { await compartilharWhatsapp(painelSlug, titulo, { indicador: indicadorId, filtrosQuery }); }
    catch (e) { alert('Erro: ' + e.message); }
    finally { gerandoPdf = false; }
  }

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

<div class="table-wrap" class:modo-relatorio={modoRelatorio}>
  {#if pivotLargoDemais}
    <p class="aviso-limite">{textoAvisoColunasPivot(pivotCtx.valores.length)}</p>
  {:else}
  <table>
    <thead>
      <tr>
        {#each colunasDetalhe as col}<th>{col.label ?? col.key}</th>{/each}
        {#each agregacoesEfetivas as ag}<th class="agregado-header">{ag.label ?? ag.coluna}</th>{/each}
        {#if mostrarAcoes}<th>Ações</th>{/if}
      </tr>
    </thead>
    <tbody>
      <GrupoLinha
        no={arvore} {colunasDetalhe} agregacoes={agregacoesEfetivas} {mostrarAcoes} onAcionar={acionar}
        nivel={0} modo="tabela" ocultarFolhas={ocultarDetalhe} expandidos={expandidosEfetivo} onAlternar={alternar} caminho=""
      />
    </tbody>
  </table>
  {/if}

  {#if !modoRelatorio}
  <div class="cards-mobile">
    <GrupoLinha
      no={arvore} {colunasDetalhe} agregacoes={agregacoesEfetivas} {mostrarAcoes} onAcionar={acionar}
      nivel={0} modo="cards" expandidos={expandidosEfetivo} onAlternar={alternar} caminho=""
    />
  </div>
  {/if}
  {#if ocultarDetalhe && !pivotLargoDemais}
    <p class="aviso-limite">{textoAvisoLimite(dados.length, 'omitir-detalhe')}</p>
  {/if}

  {#if !modoRelatorio}
  <div class="export-bar">
    <button class="btn-export btn-export-csv btn-sm" on:click={() => baixarCSVAgrupado(colunasDetalhe, agregacoesEfetivas, arvore, titulo)} disabled={dados.length === 0}>
      ⬇ CSV
    </button>
    <button class="btn-export btn-export-xlsx btn-sm" on:click={() => baixarXLSXAgrupado(colunasDetalhe, agregacoesEfetivas, arvore, titulo)} disabled={dados.length === 0}>
      ⬇ Excel
    </button>
    {#if painelSlug}
    <button class="btn-export btn-export-pdf btn-sm" on:click={exportarPDF} disabled={dados.length === 0 || gerandoPdf}>
      {gerandoPdf ? 'Gerando…' : '🖨 PDF'}
    </button>
    {#if compartilhavel}
    <button class="btn-export btn-export-pdf btn-sm" on:click={enviarWhatsapp} disabled={dados.length === 0 || gerandoPdf}>
      WhatsApp
    </button>
    {/if}
    {/if}
  </div>
  {/if}
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
.aviso-limite { margin: 8px 0 0; font-size: 11px; color: var(--muted); font-style: italic; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; letter-spacing: .06em; color: var(--muted); }
.agregado-header { text-align: right; }
.error { color: var(--danger, #f85149); }

.export-bar { display: flex; gap: 8px; padding: 12px 0 0; flex-wrap: wrap; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.btn-export { color: #0d1117; font-weight: 600; border: none; }
.btn-export-csv { background: var(--accent); }
.btn-export-xlsx { background: var(--accent-blue); color: #fff; }
.btn-export-pdf { background: var(--danger, #f85149); color: #fff; }

.cards-mobile { display: none; }

.modo-relatorio { overflow: visible; }
.modo-relatorio table { font-size: 11px; }
.modo-relatorio th, .modo-relatorio td { white-space: normal; overflow-wrap: anywhere; padding: 6px 8px; }
.modo-relatorio .cards-mobile { display: none; }

@media (max-width: 768px) {
  table { display: none; }
  .cards-mobile { display: flex; flex-direction: column; gap: 4px; }
}
</style>
