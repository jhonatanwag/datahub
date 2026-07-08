# Reordenar Indicadores do Painel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar botões ▲/▼ em cada indicador da aba "Indicadores" (`/configuracoes/paineis/[id]`), permitindo trocar qual query ocupa cada slot da grade sem editar os campos `linha`/`coluna` manualmente.

**Architecture:** Troca de conteúdo (não de posição): os botões trocam `query_slug`, `titulo` e `posicao` entre o indicador clicado e seu vizinho adjacente no array `indicadores`, mantendo `linha`/`coluna`/`col_span`/`row_span` intactos em cada slot. Sem mudança de API — a troca é só estado local do form Svelte, persistida pelo fluxo de "Salvar Alterações" já existente (`api.salvarIndicadores`).

**Tech Stack:** SvelteKit (JS puro, Svelte 5)

## Global Constraints

- JS puro — sem TypeScript
- Nenhuma chamada de API nova — reutiliza `api.salvarIndicadores` já existente no `salvar()`
- `linha`/`coluna`/`col_span`/`row_span` de cada slot nunca mudam pela troca — só `query_slug`, `titulo`, `posicao`
- Reusar classes CSS existentes (`.btn-ghost`, `.btn-sm`) — sem CSS novo
- Sem framework de testes no frontend — verificação manual/Playwright real (padrão já estabelecido no projeto)
- Frontend roda em Docker: `datahub_frontend` (bind-mount, `docker restart datahub_frontend` após editar `.svelte`)

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte` | Modificar | Função `moverIndicador` + botões ▲/▼ no template |

---

## Task 1: Botões de reordenar indicadores

**Files:**
- Modify: `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte:95` (nova função, logo após `removerIndicador`)
- Modify: `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte:246` (bloco `.ind-row`)

**Interfaces:**
- Consumes: array reativo `indicadores` já existente no componente (cada item: `{query_slug, titulo, linha, coluna, col_span, row_span, posicao}`)
- Produces: `moverIndicador(i, direcao)` — troca `query_slug`/`titulo`/`posicao` entre `indicadores[i]` e `indicadores[i + direcao]`; usado pelos novos botões ▲ (`direcao = -1`) e ▼ (`direcao = 1`)

- [ ] **Step 1: Adicionar a função `moverIndicador` logo após `removerIndicador`**

```javascript
// frontend/src/routes/configuracoes/paineis/[id]/+page.svelte — linha ~95-97
function removerIndicador(i) {
  indicadores = indicadores.filter((_, idx) => idx !== i);
}

function moverIndicador(i, direcao) {
  const j = i + direcao;
  if (j < 0 || j >= indicadores.length) return;
  const a = indicadores[i];
  const b = indicadores[j];
  [a.query_slug, b.query_slug] = [b.query_slug, a.query_slug];
  [a.titulo, b.titulo]         = [b.titulo, a.titulo];
  [a.posicao, b.posicao]       = [b.posicao, a.posicao];
  indicadores = [...indicadores];
}
```

- [ ] **Step 2: Adicionar os botões ▲/▼ no template, dentro do `.ind-row`, antes do botão ✕ existente**

```svelte
<!-- frontend/src/routes/configuracoes/paineis/[id]/+page.svelte — dentro de {#each indicadores as ind, i}, linha ~246 -->
<div class="ind-row">
  <div class="field flex-1">
    <label>Query</label>
    <select bind:value={ind.query_slug}>
      {#each queries as q}
        <option value={q.slug}>{q.nome} ({q.tipo})</option>
      {/each}
    </select>
  </div>
  <button class="btn-ghost btn-sm" on:click={() => moverIndicador(i, -1)} disabled={i === 0} title="Mover pra cima">▲</button>
  <button class="btn-ghost btn-sm" on:click={() => moverIndicador(i, 1)} disabled={i === indicadores.length - 1} title="Mover pra baixo">▼</button>
  <button class="btn-ghost btn-sm danger" on:click={() => removerIndicador(i)}>✕</button>
</div>
```

- [ ] **Step 3: Reiniciar o frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 4: Verificação manual completa (real, em navegador)**

Usar o painel seed `visao_geral` (id 1), que já tem múltiplos indicadores em dev:

1. Abrir `http://localhost:3000/configuracoes/paineis/1`, ir na aba "Indicadores".
2. Confirmar: botão ▲ do primeiro indicador da lista está desabilitado; botão ▼ do último está desabilitado.
3. Anotar o `query_slug` (visível no dropdown "Query") do 1º e 2º indicador da lista.
4. Clicar ▲ no 2º indicador — confirmar que os dropdowns de Query do 1º e 2º trocaram de valor (o que estava no 2º agora aparece no 1º, e vice-versa), e que os campos Linha/Coluna/Col Span/Row Span de cada posição **não mudaram**.
5. Confirmar que o preview do grid (painel direito da aba) reflete a troca imediatamente, sem precisar salvar.
6. Clicar ▼ no 1º indicador — confirmar que volta ao estado original (troca é reversível).
7. Clicar "Salvar Alterações", recarregar a página, voltar na aba Indicadores — confirmar que a ordem trocada persistiu (prova que `api.salvarIndicadores` grava `query_slug`/`titulo`/`posicao` corretamente sem mudança de API).
8. Confirmar que outras abas (Configurações Gerais, Filtros e Acesso) e o fluxo de adicionar/remover indicador continuam funcionando sem regressão.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/routes/configuracoes/paineis/[id]/+page.svelte"
git commit -m "feat: add up/down reorder buttons to painel indicators"
```

---

## Verificação Final

- [ ] Botões ▲/▼ aparecem em cada indicador, desabilitados corretamente nas pontas da lista
- [ ] Troca de conteúdo funciona nos dois sentidos e é visível no preview sem salvar
- [ ] `linha`/`coluna`/`col_span`/`row_span` de cada slot nunca mudam pela troca
- [ ] Persistência após salvar + recarregar funciona
- [ ] Sem regressão nas outras abas ou no fluxo de adicionar/remover indicador
