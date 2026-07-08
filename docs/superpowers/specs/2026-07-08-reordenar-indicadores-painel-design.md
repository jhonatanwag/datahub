# Reordenar indicadores (▲/▼) em `/configuracoes/paineis/[id]` — Design

## Contexto

Na aba "Indicadores" da tela de edição de painel (`frontend/src/routes/configuracoes/paineis/[id]/+page.svelte`), cada indicador tem posição definida por `linha`/`coluna`/`col_span`/`row_span` (grid CSS), não pela ordem em que aparece na lista de edição. Ao clicar "+ Adicionar Indicador", o novo item recebe `linha: indicadores.length + 1, coluna: 1` — ou seja, no caso comum (um indicador por linha, sem customizar colunas), a ordem de adição já determina a ordem visual no painel. Hoje, mudar essa ordem exige editar manualmente os números de `Linha` em cada indicador. O pedido: botões ▲/▼ para reordenar sem editar números à mão.

## Decisão de comportamento

Como a posição real é `linha`/`coluna`/`col_span`/`row_span` (não a ordem do array), os botões **trocam qual query ocupa o slot**, não a posição em si:

- Clicar ▲ no indicador do índice `i` troca `query_slug`, `titulo` e `posicao` com o indicador do índice `i - 1`.
- Clicar ▼ troca com o índice `i + 1`.
- `linha`, `coluna`, `col_span`, `row_span` de cada slot **não mudam** — só o conteúdo que ocupa aquele slot.

Isso é seguro em qualquer layout: no caso comum (um indicador por linha), o efeito é indistinguível de "mover a linha pra cima/baixo". Em layouts com múltiplas colunas/spans customizados, evita qualquer corrupção de tamanho de célula — o card muda de conteúdo, não de forma.

**Fora de escopo:** mudar `linha`/`coluna` diretamente com os botões (o campo numérico continua existindo pra isso); qualquer chamada de API nova (a troca é só estado local do form, persiste no "Salvar Alterações" já existente via `api.salvarIndicadores`).

## Implementação

### `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte`

Nova função, ao lado de `adicionarIndicador`/`removerIndicador`:

```javascript
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

No template, dentro de `.ind-row` (ao lado do botão ✕ existente), adicionar dois botões antes dele:

```svelte
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

Nenhuma mudança de CSS nova é necessária — `.btn-ghost`/`.btn-sm` já existem e já são usados no botão ✕ ao lado.

### Verificação

- Painel com 3+ indicadores (usar o painel seed `visao_geral`/id 1, que já tem múltiplos indicadores em produção de dev): clicar ▲ no segundo indicador deve trocar seu conteúdo com o primeiro; o preview do grid abaixo reflete a troca imediatamente (reatividade já existe, sem mudança extra).
- ▲ desabilitado no primeiro indicador da lista; ▼ desabilitado no último.
- Salvar após reordenar e recarregar a página — a nova ordem persiste (confirma que `salvarIndicadores` já grava `query_slug`/`titulo`/`posicao` corretamente, sem mudança de API necessária).
- Indicador único (lista com 1 item) — ambos os botões ficam desabilitados, sem erro.
