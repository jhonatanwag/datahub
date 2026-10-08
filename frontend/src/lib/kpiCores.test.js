import { test } from 'node:test';
import assert from 'node:assert/strict';
import { coresKpi } from './kpiCores.js';

test('cores de fábrica antigas (verde escuro / grafite) passam a seguir o tema', () => {
  assert.deepEqual(coresKpi('#2B5A45', '#F3F8F5'), { fundo: null, fonte: null });
  assert.deepEqual(coresKpi('#161b22', '#e6edf3'), { fundo: null, fonte: null });
});

test('comparação ignora maiúsculas/minúsculas', () => {
  assert.deepEqual(coresKpi('#2b5a45', '#f3f8f5'), { fundo: null, fonte: null });
});

test('cor personalizada de verdade é respeitada', () => {
  assert.deepEqual(coresKpi('#7A1F1F', '#FFFFFF'), { fundo: '#7A1F1F', fonte: '#FFFFFF' });
});

test('fundo de fábrica com fonte personalizada: fundo segue o tema, fonte é mantida', () => {
  assert.deepEqual(coresKpi('#2B5A45', '#FFD700'), { fundo: null, fonte: '#FFD700' });
});

test('sem cores definidas', () => {
  assert.deepEqual(coresKpi(null, null), { fundo: null, fonte: null });
  assert.deepEqual(coresKpi(undefined, undefined), { fundo: null, fonte: null });
});
