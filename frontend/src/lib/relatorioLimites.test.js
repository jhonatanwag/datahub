import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIMITE_LINHAS_RELATORIO, excedeLimiteRelatorio, textoAvisoLimite } from './relatorioLimites.js';

test('até o limite não excede; acima excede', () => {
  assert.equal(excedeLimiteRelatorio(0), false);
  assert.equal(excedeLimiteRelatorio(LIMITE_LINHAS_RELATORIO), false);
  assert.equal(excedeLimiteRelatorio(LIMITE_LINHAS_RELATORIO + 1), true);
});

test('limite customizado é respeitado', () => {
  assert.equal(excedeLimiteRelatorio(11, 10), true);
  assert.equal(excedeLimiteRelatorio(10, 10), false);
});

test('aviso de truncamento cita o total e o que é exibido, em pt-BR', () => {
  const t = textoAvisoLimite(39534, 'truncar');
  assert.match(t, /2\.000/);
  assert.match(t, /39\.534/);
  assert.match(t, /refine os filtros/i);
});

test('aviso de detalhe omitido explica que os totais seguem corretos', () => {
  const t = textoAvisoLimite(39534, 'omitir-detalhe');
  assert.match(t, /39\.534/);
  assert.match(t, /totais/i);
});

import { LIMITE_COLUNAS_PIVOT_RELATORIO, excedeColunasPivotRelatorio, textoAvisoColunasPivot } from './relatorioLimites.js';

test('pivô do relatório: até o limite de colunas cabe; acima não', () => {
  assert.equal(excedeColunasPivotRelatorio(LIMITE_COLUNAS_PIVOT_RELATORIO), false);
  assert.equal(excedeColunasPivotRelatorio(LIMITE_COLUNAS_PIVOT_RELATORIO + 1), true);
  assert.equal(excedeColunasPivotRelatorio(0), false);
});

test('aviso de colunas em excesso cita quantas há e o limite, e manda reduzir o período', () => {
  const t = textoAvisoColunasPivot(63);
  assert.match(t, /63/);
  assert.match(t, new RegExp(String(LIMITE_COLUNAS_PIVOT_RELATORIO)));
  assert.match(t, /período/i);
});
