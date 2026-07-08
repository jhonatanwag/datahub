# Ordenação por coluna em Queries/Variáveis/Usuários — Design

## Contexto

As telas `/configuracoes/queries`, `/configuracoes/variaveis` e `/configuracoes/usuarios` listam registros em tabelas HTML simples, sem nenhuma forma de ordenar por coluna — a ordem é sempre a que vem da API. O pedido: clicar no cabeçalho de uma coluna ordena a lista por aquela coluna.

## Decisões

- **Toggle de 3 estados por coluna:** 1º clique ordena crescente, 2º clique decrescente, 3º clique remove a ordenação (volta à ordem original da API/filtro). Clicar em outra coluna sempre reinicia no estado crescente para a nova coluna.
- **Lógica de comparação compartilhada:** `frontend/src/lib/sort.js`, usado pelas 3 páginas, para não reescrever comparação de string/número/booleano três vezes.
- **Sem componente de cabeçalho compartilhado:** as 3 tabelas têm estruturas/estilos diferentes (a de queries usa `style` inline dentro de um `{#each}` de nomes de coluna; variáveis/usuários usam `<th>` estáticos com classes de `<style>` escopado) — extrair um componente forçaria unificar esses dois estilos sem necessidade. Cada página implementa seu próprio clique de cabeçalho, reusando só a função de comparação.
- **Coluna "Ações" (e colunas de lista livre sem ordem natural — "Parâmetros" em Variáveis, "Empresas" em Usuários) não são clicáveis.**
- **Em Queries, a ordenação atua sobre a lista já filtrada por Tipo**, não sobre a lista bruta da API.

## `frontend/src/lib/sort.js`

```javascript
export function compararValores(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  if (typeof a === 'boolean' || typeof b === 'boolean') {
    return (a === b) ? 0 : (a ? 1 : -1);
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  return String(a).localeCompare(String(b), 'pt-BR', { sensitivity: 'base' });
}

export function ordenarLista(lista, campo, direcao, extrator = (item, c) => item[c]) {
  if (!campo || !direcao) return lista;
  const copia = [...lista];
  copia.sort((a, b) => {
    const cmp = compararValores(extrator(a, campo), extrator(b, campo));
    return direcao === 'asc' ? cmp : -cmp;
  });
  return copia;
}

export function proximaDirecao(campoClicado, campoAtual, direcaoAtual) {
  if (campoClicado !== campoAtual) return 'asc';
  if (direcaoAtual === 'asc') return 'desc';
  if (direcaoAtual === 'desc') return null;
  return 'asc';
}
```

- `extrator` permite cada página mapear o nome da coluna clicável pro valor real usado na comparação (ex: "Escopo" → `q.empresa_id`, "Status" → `u.ativo`), sem precisar que a estrutura do objeto já tenha esse campo pronto com esse nome.

## Por página

### `frontend/src/routes/configuracoes/queries/+page.svelte`

- Estado: `let ordenarCampo = null; let ordenarDirecao = null;`
- Colunas clicáveis → chave de extração: `slug`, `nome`, `tipo`, `cache_ttl`, `empresa_id` (rótulo "Escopo"), `ativo`.
- `$: ordenadas = ordenarLista(filtradas, ordenarCampo, ordenarDirecao)` — encadeia depois do filtro por tipo já existente (`filtradas`).
- Cabeçalho atual é gerado via `{#each ['Slug', 'Nome', ...] as h}` com `<th>` genérico — precisa virar uma lista de objetos `{label, campo}` (campo `null` para "Ações") pra saber em qual coluna clicar e qual extrair.
- Renderizar `{#each ordenadas as q}` no lugar de `{#each filtradas as q}`.

### `frontend/src/routes/configuracoes/variaveis/+page.svelte`

- Colunas clicáveis → chave: `slug`, `nome`, `tipo`, `query_fonte` (booleano: presença ou não).
- "Parâmetros" e "Ações" não clicáveis.
- `$: ordenadas = ordenarLista(variaveis, ordenarCampo, ordenarDirecao)`.

### `frontend/src/routes/configuracoes/usuarios/+page.svelte`

- Colunas clicáveis → chave: `nome`, `email`, `role` (rótulo "Perfil"), `ativo` (rótulo "Status").
- "Empresas" e "Ações" não clicáveis.
- `$: ordenadas = ordenarLista(usuarios, ordenarCampo, ordenarDirecao)`.

## Visual

Cabeçalho clicável: `cursor: pointer`, leve destaque no hover (reusa `color: var(--text)` no hover, igual ao `.tab:hover` já usado em outras telas do projeto). Coluna ativa mostra uma seta depois do texto: `▲` (asc) ou `▼` (desc). Sem seta quando a coluna não é a ativa, ou quando o 3º clique resetou a ordenação.

## Fora de escopo

- Ordenação multi-coluna (segurar Shift e clicar em duas colunas, por exemplo).
- Persistir a ordenação escolhida (recarregar a página volta ao estado sem ordenação).
- Ordenar "Parâmetros"/"Empresas" (listas livres sem ordem natural clara).

## Verificação

- Clicar em cada cabeçalho clicável das 3 telas — 1º clique ordena crescente (seta ▲), 2º decrescente (seta ▼), 3º remove a ordenação (sem seta, volta à ordem original).
- Clicar em uma coluna diferente enquanto outra está ordenada — a nova coluna assume o estado crescente, a seta antiga desaparece.
- Em Queries: aplicar um filtro de Tipo com uma coluna já ordenada — a ordenação continua válida sobre a lista filtrada.
- "Ações" (nas 3 telas), "Parâmetros" (Variáveis) e "Empresas" (Usuários) não reagem a clique.
- Nenhuma mudança de API — tudo client-side sobre os dados já carregados.
