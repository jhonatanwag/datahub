import { test } from 'node:test';
import assert from 'node:assert/strict';
import { calcularAgregacoes, construirArvore, montarPivot } from './tabelaDinamica.js';

// Uma linha = uma resposta "NAO" do checklist.
const DADOS = [
  { ficha: 'F1', pergunta: 'P1', mes: 'FEV/2026', mes_ord: 202602, qtd: 1 },
  { ficha: 'F1', pergunta: 'P1', mes: 'JAN/2026', mes_ord: 202601, qtd: 1 },
  { ficha: 'F1', pergunta: 'P1', mes: 'JAN/2026', mes_ord: 202601, qtd: 1 },
  { ficha: 'F1', pergunta: 'P2', mes: 'JAN/2026', mes_ord: 202601, qtd: 1 },
  { ficha: 'F2', pergunta: 'P3', mes: 'FEV/2026', mes_ord: 202602, qtd: 1 },
];
const AGREG = [{ coluna: 'qtd', funcao: 'soma', label: 'Qtd.' }];
const CFG = { coluna: 'mes', ordem_coluna: 'mes_ord', total: true };

test('sem pivô o comportamento de agrupamento é o de sempre', () => {
  const arvore = construirArvore(DADOS, 0, ['ficha'], AGREG, null);
  assert.equal(arvore.grupos.length, 2);
  assert.deepEqual(arvore.grupos[0].agregados, [{ coluna: 'qtd', label: 'Qtd.', valor: 4 }]);
  assert.equal(arvore.totalGeral, undefined);
});

test('montarPivot devolve null sem configuração', () => {
  assert.equal(montarPivot(DADOS, null, AGREG), null);
  assert.equal(montarPivot(DADOS, { coluna: null }, AGREG), null);
});

test('colunas do pivô saem ordenadas pela coluna de ordem, não pela ordem das linhas', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  assert.deepEqual(p.valores, ['JAN/2026', 'FEV/2026']);
});

test('sem coluna de ordem as colunas seguem a ordem de aparição', () => {
  const p = montarPivot(DADOS, { coluna: 'mes', total: false }, AGREG);
  assert.deepEqual(p.valores, ['FEV/2026', 'JAN/2026']);
});

test('grupo ganha uma célula por valor do pivô e o total', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  const arvore = construirArvore(DADOS, 0, ['ficha', 'pergunta'], AGREG, p);
  const f1 = arvore.grupos[0];
  assert.deepEqual(
    f1.agregados.map(a => [a.label, a.valor]),
    [['JAN/2026', 3], ['FEV/2026', 1], ['Total Geral', 4]],
  );
  const p1 = f1.filho.grupos[0];
  assert.deepEqual(p1.agregados.map(a => a.valor), [2, 1, 3]);
});

test('mês sem ocorrência fica vazio (null), não zero', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  const arvore = construirArvore(DADOS, 0, ['ficha', 'pergunta'], AGREG, p);
  const p2 = arvore.grupos[0].filho.grupos[1]; // P2 só tem JAN
  assert.deepEqual(p2.agregados.map(a => a.valor), [1, null, 1]);
});

test('células do pivô já vêm sem rótulo (o cabeçalho da coluna carrega o nome)', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  const arvore = construirArvore(DADOS, 0, ['ficha'], AGREG, p);
  assert.ok(arvore.grupos[0].agregados.every(a => a.semRotulo === true));
});

test('raiz carrega o Total Geral quando pivot.total está ligado', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  const arvore = construirArvore(DADOS, 0, ['ficha'], AGREG, p);
  assert.deepEqual(arvore.totalGeral.map(a => a.valor), [3, 2, 5]);
});

test('sem pivot.total não há coluna Total nem Total Geral', () => {
  const p = montarPivot(DADOS, { ...CFG, total: false }, AGREG);
  const arvore = construirArvore(DADOS, 0, ['ficha'], AGREG, p);
  assert.deepEqual(arvore.grupos[0].agregados.map(a => a.label), ['JAN/2026', 'FEV/2026']);
  assert.equal(arvore.totalGeral, undefined);
});

test('cabeçalhos do pivô servem de "agregações" pra tabela (mesma contagem de colunas)', () => {
  const p = montarPivot(DADOS, CFG, AGREG);
  assert.deepEqual(p.cabecalhos.map(c => c.label), ['JAN/2026', 'FEV/2026', 'Total Geral']);
});

test('usa a primeira agregação; sem nenhuma, conta linhas', () => {
  const semAgreg = montarPivot(DADOS, CFG, []);
  const arvore = construirArvore(DADOS, 0, ['ficha'], [], semAgreg);
  assert.deepEqual(arvore.grupos[0].agregados.map(a => a.valor), [3, 1, 4]);
});

test('valor nulo no pivô vira coluna "—"', () => {
  const dados = [{ ficha: 'F1', mes: null, qtd: 1 }, { ficha: 'F1', mes: 'JAN', qtd: 1 }];
  const p = montarPivot(dados, { coluna: 'mes' }, AGREG);
  assert.deepEqual(p.valores, [null, 'JAN']);
  assert.equal(p.cabecalhos[0].label, '—');
});

test('calcularAgregacoes segue igual: ignora valores não numéricos', () => {
  const r = calcularAgregacoes([{ qtd: 2 }, { qtd: 'x' }, { qtd: 3 }], AGREG);
  assert.equal(r[0].valor, 5);
});
