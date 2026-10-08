import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PAUSA_ROLAGEM_SEG, VELOCIDADE_MAX_PX_SEG,
  planoRolagem, posicaoRolagem, proximoIndice, anteriorIndice, precisaAtualizar, filtrosEfetivos, criarControleDeGeracao,
} from './apresentacao.js';

const perto = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test('conteúdo que cabe na tela não rola nem estende o tempo', () => {
  const p = planoRolagem({ alturaConteudo: 800, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.rola, false);
  assert.equal(p.tempoTotalSeg, 30);
  assert.equal(posicaoRolagem(p, 15), 0);
});

test('diferença de 1px (arredondamento) não conta como rolagem', () => {
  assert.equal(planoRolagem({ alturaConteudo: 901, alturaViewport: 900, duracaoSeg: 30 }).rola, false);
});

test('rolagem cabe no tempo configurado (descontadas as pausas)', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.rola, true);
  assert.equal(p.distancia, 1000);
  perto(p.velocidade, 1000 / (30 - 2 * PAUSA_ROLAGEM_SEG));
  assert.equal(p.tempoTotalSeg, 30);
});

test('conteúdo gigante: velocidade limitada ao teto e tempo estendido', () => {
  const p = planoRolagem({ alturaConteudo: 9900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.velocidade, VELOCIDADE_MAX_PX_SEG);
  perto(p.duracaoRolagemSeg, 9000 / VELOCIDADE_MAX_PX_SEG);
  perto(p.tempoTotalSeg, 9000 / VELOCIDADE_MAX_PX_SEG + 2 * PAUSA_ROLAGEM_SEG);
  assert.ok(p.tempoTotalSeg > 30);
});

test('duração curta (5s) não gera velocidade infinita', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 5 });
  assert.ok(Number.isFinite(p.velocidade) && p.velocidade <= VELOCIDADE_MAX_PX_SEG);
});

test('posição: espera no topo, rola, trava no fim', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(posicaoRolagem(p, 0), 0);
  assert.equal(posicaoRolagem(p, PAUSA_ROLAGEM_SEG), 0);
  perto(posicaoRolagem(p, PAUSA_ROLAGEM_SEG + 10), 10 * p.velocidade);
  assert.equal(posicaoRolagem(p, 29), 1000);
});

test('índices circulares', () => {
  assert.equal(proximoIndice(0, 3), 1);
  assert.equal(proximoIndice(2, 3), 0);
  assert.equal(anteriorIndice(0, 3), 2);
  assert.equal(anteriorIndice(2, 3), 1);
  assert.equal(proximoIndice(0, 0), 0);
  assert.equal(anteriorIndice(0, 0), 0);
  assert.equal(proximoIndice(0, 1), 0);
});

test('precisaAtualizar respeita o intervalo', () => {
  assert.equal(precisaAtualizar(0, 299_000, 300), false);
  assert.equal(precisaAtualizar(0, 300_000, 300), true);
});

test('filtrosEfetivos: tokens resolvidos na data de agora, override vence', () => {
  const dia8 = new Date(2026, 9, 8), dia9 = new Date(2026, 9, 9);
  const raw = { data: 'hoje', setor: 'Lavoura' };
  assert.deepEqual(filtrosEfetivos(raw, {}, dia8), { data: '2026-10-08', setor: 'Lavoura' });
  assert.deepEqual(filtrosEfetivos(raw, {}, dia9), { data: '2026-10-09', setor: 'Lavoura' });
  assert.deepEqual(filtrosEfetivos(raw, { setor: 'Sede' }, dia8), { data: '2026-10-08', setor: 'Sede' });
  assert.deepEqual(filtrosEfetivos(raw, undefined, dia8), { data: '2026-10-08', setor: 'Lavoura' });
});

test('controle de geração: resposta antiga do mesmo slide é descartada', () => {
  const g = criarControleDeGeracao();
  const primeira = g.iniciar(7);
  const segunda = g.iniciar(7);
  assert.equal(g.valida(7, primeira), false);
  assert.equal(g.valida(7, segunda), true);
});

test('controle de geração: slides diferentes não se invalidam', () => {
  const g = criarControleDeGeracao();
  const a = g.iniciar(1);
  g.iniciar(2);
  assert.equal(g.valida(1, a), true);
});
