import { resolverFiltros } from './filtrosPainel.js';

export const PAUSA_ROLAGEM_SEG = 3;          // parada no topo e no fim do slide
export const VELOCIDADE_MAX_PX_SEG = 80;     // teto pra manter legível
export const RENOVAR_TOKEN_MS = 30 * 60 * 1000;

// Plano de rolagem de um slide. `duracaoSeg` é o MÍNIMO: se a rolagem (limitada
// ao teto de velocidade) não couber, o slide se estende até o fim da rolagem.
export function planoRolagem({ alturaConteudo, alturaViewport, duracaoSeg }) {
  const distancia = Math.max(0, alturaConteudo - alturaViewport);
  if (distancia < 2) {
    return { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: duracaoSeg };
  }
  const disponivel = Math.max(duracaoSeg - 2 * PAUSA_ROLAGEM_SEG, 1);
  const velocidade = Math.min(distancia / disponivel, VELOCIDADE_MAX_PX_SEG);
  const duracaoRolagemSeg = distancia / velocidade;
  return {
    rola: true,
    distancia,
    velocidade,
    duracaoRolagemSeg,
    tempoTotalSeg: Math.max(duracaoSeg, duracaoRolagemSeg + 2 * PAUSA_ROLAGEM_SEG),
  };
}

export function posicaoRolagem(plano, decorridoSeg) {
  if (!plano.rola) return 0;
  const t = decorridoSeg - PAUSA_ROLAGEM_SEG;
  if (t <= 0) return 0;
  return Math.min(plano.distancia, t * plano.velocidade);
}

export const proximoIndice  = (atual, total) => (total <= 0 ? 0 : (atual + 1) % total);
export const anteriorIndice = (atual, total) => (total <= 0 ? 0 : (atual - 1 + total) % total);

export const precisaAtualizar = (ultimaMs, agoraMs, intervaloSeg) => agoraMs - ultimaMs >= intervaloSeg * 1000;

// Filtros usados na consulta: tokens do slide resolvidos AGORA + o que o usuário editou.
export function filtrosEfetivos(raw, override, agora = new Date()) {
  return { ...resolverFiltros(raw, agora), ...(override ?? {}) };
}

// Evita que a resposta de uma requisição mais lenta (e mais antiga) do mesmo slide
// sobrescreva a de uma requisição mais nova (ex.: filtro aplicado durante um refresh).
export function criarControleDeGeracao() {
  const atual = {};
  return {
    iniciar(id) { atual[id] = (atual[id] ?? 0) + 1; return atual[id]; },
    valida(id, n) { return atual[id] === n; },
  };
}
