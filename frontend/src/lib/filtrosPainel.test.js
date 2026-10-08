import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolverToken, valoresIniciais, resolverFiltros, chavesFiltro } from './filtrosPainel.js';

const OUT_8 = new Date(2026, 9, 8); // 08/10/2026

test('tokens do mês e do dia', () => {
  assert.equal(resolverToken('hoje', OUT_8), '2026-10-08');
  assert.equal(resolverToken('ontem', OUT_8), '2026-10-07');
  assert.equal(resolverToken('mes_atual_inicio', OUT_8), '2026-10-01');
  assert.equal(resolverToken('mes_atual_fim', OUT_8), '2026-10-31');
  assert.equal(resolverToken('mes_anterior_inicio', OUT_8), '2026-09-01');
  assert.equal(resolverToken('mes_anterior_fim', OUT_8), '2026-09-30');
  assert.equal(resolverToken('ano_atual_inicio', OUT_8), '2026-01-01');
  assert.equal(resolverToken('ano_atual_fim', OUT_8), '2026-12-31');
});

test('janeiro olha dezembro do ano anterior; virada de ano em "ontem"', () => {
  const jan = new Date(2026, 0, 1);
  assert.equal(resolverToken('mes_anterior_inicio', jan), '2025-12-01');
  assert.equal(resolverToken('mes_anterior_fim', jan), '2025-12-31');
  assert.equal(resolverToken('ontem', jan), '2025-12-31');
});

test('valor que não é token passa direto; vazio vira string vazia', () => {
  assert.equal(resolverToken('Lavoura', OUT_8), 'Lavoura');
  assert.equal(resolverToken('', OUT_8), '');
  assert.equal(resolverToken(undefined, OUT_8), '');
});

test('valoresIniciais separa date_range em _inicio/_fim', () => {
  const v = valoresIniciais([
    { tipo: 'date_range', slug: 'periodo', valor_padrao_inicio: 'mes_atual_inicio', valor_padrao_fim: 'hoje' },
    { tipo: 'text', slug: 'busca', valor_padrao: 'abc' },
    { tipo: 'select', slug: 'setor' },
  ], OUT_8);
  assert.deepEqual(v, { periodo_inicio: '2026-10-01', periodo_fim: '2026-10-08', busca: 'abc', setor: '' });
});

test('resolverFiltros resolve todos os valores', () => {
  assert.deepEqual(
    resolverFiltros({ periodo_inicio: 'mes_atual_inicio', setor: 'Lavoura' }, OUT_8),
    { periodo_inicio: '2026-10-01', setor: 'Lavoura' },
  );
  assert.deepEqual(resolverFiltros(undefined, OUT_8), {});
});

test('chavesFiltro', () => {
  assert.deepEqual(
    chavesFiltro({ tipo: 'date_range', slug: 'periodo', nome: 'Período' }).map(c => c.chave),
    ['periodo_inicio', 'periodo_fim'],
  );
  assert.deepEqual(chavesFiltro({ tipo: 'select', slug: 'setor', nome: 'Setor' }), [{ chave: 'setor', rotulo: 'Setor' }]);
});
