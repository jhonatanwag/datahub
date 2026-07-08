# Ordenação por Coluna nas Listas de Configuração Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir ordenar as tabelas de `/configuracoes/queries`, `/configuracoes/variaveis` e `/configuracoes/usuarios` clicando no cabeçalho de uma coluna (toggle de 3 estados: crescente → decrescente → sem ordenação).

**Architecture:** Um utilitário compartilhado (`frontend/src/lib/sort.js`) concentra a lógica de comparação e o toggle de estado; cada página aplica isso sobre seus próprios dados já carregados (sem chamada de API nova), com cabeçalhos clicáveis específicos de cada tabela (estruturas diferentes entre as 3 páginas).

**Tech Stack:** SvelteKit (JS puro, Svelte 5)

## Global Constraints

- JS puro — sem TypeScript
- Nenhuma chamada de API nova — ordenação 100% client-side sobre dados já carregados
- Toggle de 3 estados por coluna: clique 1 = `asc`, clique 2 = `desc`, clique 3 = remove ordenação (`null`/`null`). Clicar em coluna diferente sempre reinicia em `asc` pra ela.
- Coluna "Ações" nunca é clicável, em nenhuma das 3 telas
- Em Variáveis, "Parâmetros" não é clicável; em Usuários, "Empresas" não é clicável (listas livres sem ordem natural)
- Seta visual: `▲` quando a coluna está ordenada crescente, `▼` quando decrescente, nada quando não é a coluna ativa
- Sem framework de testes no frontend — verificação manual/Playwright real

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `frontend/src/lib/sort.js` | Criar | `compararValores`, `ordenarLista`, `proximaDirecao` — lógica de comparação e toggle compartilhada |
| `frontend/src/routes/configuracoes/queries/+page.svelte` | Modificar | Cabeçalhos clicáveis + `ordenadas` sobre `filtradas` |
| `frontend/src/routes/configuracoes/variaveis/+page.svelte` | Modificar | Cabeçalhos clicáveis + `ordenadas` sobre `variaveis` |
| `frontend/src/routes/configuracoes/usuarios/+page.svelte` | Modificar | Cabeçalhos clicáveis + `ordenadas` sobre `usuarios` |

---

## Task 1: Utilitário compartilhado de ordenação

**Files:**
- Create: `frontend/src/lib/sort.js`

**Interfaces:**
- Produces: `compararValores(a, b)` — comparador genérico (string/número/booleano/null); `ordenarLista(lista, campo, direcao, extrator?)` — retorna cópia ordenada ou a lista original se `campo`/`direcao` forem `null`; `proximaDirecao(campoClicado, campoAtual, direcaoAtual)` — calcula o próximo estado do toggle de 3 cliques. Usado pelas Tasks 2, 3 e 4.

- [ ] **Step 1: Criar o arquivo com as três funções**

```javascript
// frontend/src/lib/sort.js
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

- [ ] **Step 2: Verificação manual rápida via node**

```bash
docker exec datahub_frontend node -e "
const { compararValores, ordenarLista, proximaDirecao } = require('/app/src/lib/sort.js');
" 2>&1 || echo "esperado: ESM não roda com require — validar via import no navegador na Task 2"
```

Como o arquivo usa `export`/ESM (padrão do resto do projeto, ex: `$lib/api.js`), a validação real acontece integrada nas Tasks 2-4 (import direto nas páginas `.svelte`). Este step é só pra confirmar que o arquivo foi criado no caminho certo:

```bash
docker exec datahub_frontend test -f /app/src/lib/sort.js && echo "arquivo existe"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/sort.js
git commit -m "feat: add shared sort utility for config list tables"
```

---

## Task 2: Ordenação em `/configuracoes/queries`

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/+page.svelte`

**Interfaces:**
- Consumes: `ordenarLista`, `proximaDirecao` de `frontend/src/lib/sort.js` (Task 1); `filtradas` (array já existente, resultado do filtro por Tipo)
- Produces: `ordenadas` — array renderizado na tabela, substituindo `filtradas` no `{#each}`

- [ ] **Step 1: Importar o utilitário e adicionar estado de ordenação**

```javascript
// frontend/src/routes/configuracoes/queries/+page.svelte — topo do <script>, linha ~1-8
import { onMount } from 'svelte';
import { api } from '$lib/api.js';
import { ordenarLista, proximaDirecao } from '$lib/sort.js';

let queries     = [];
let filtroTipo  = '';
let loading     = true;
let erro        = null;
let ordenarCampo    = null;
let ordenarDirecao  = null;
```

- [ ] **Step 2: Definir as colunas clicáveis e a função de clique, e encadear a ordenação sobre `filtradas`**

```javascript
// frontend/src/routes/configuracoes/queries/+page.svelte — logo após a declaração de `tipos` (linha ~19)
const colunas = [
  { label: 'Slug',       campo: 'slug' },
  { label: 'Nome',       campo: 'nome' },
  { label: 'Tipo',       campo: 'tipo' },
  { label: 'Cache TTL',  campo: 'cache_ttl' },
  { label: 'Escopo',     campo: 'empresa_id' },
  { label: 'Ativo',      campo: 'ativo' },
  { label: 'Ações',      campo: null },
];

function onClickColuna(campo) {
  if (!campo) return;
  ordenarDirecao = proximaDirecao(campo, ordenarCampo, ordenarDirecao);
  ordenarCampo = ordenarDirecao ? campo : null;
}
```

```javascript
// frontend/src/routes/configuracoes/queries/+page.svelte — linha ~31, logo após `$: filtradas = ...`
$: filtradas = filtroTipo ? queries.filter(q => q.tipo === filtroTipo) : queries;
$: ordenadas = ordenarLista(filtradas, ordenarCampo, ordenarDirecao);
```

- [ ] **Step 3: Trocar o cabeçalho gerado por array de strings pelo novo array de colunas, com clique e seta**

```svelte
<!-- frontend/src/routes/configuracoes/queries/+page.svelte — linha ~78-83, dentro de <thead> -->
<thead>
  <tr>
    {#each colunas as c}
      <th
        style="padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); font-size:11px; text-transform:uppercase; color:var(--muted); {c.campo ? 'cursor:pointer' : ''}"
        on:click={() => onClickColuna(c.campo)}
      >
        {c.label}{#if ordenarCampo === c.campo}{ordenarDirecao === 'asc' ? ' ▲' : ' ▼'}{/if}
      </th>
    {/each}
  </tr>
</thead>
```

- [ ] **Step 4: Renderizar `ordenadas` no lugar de `filtradas`**

```svelte
<!-- frontend/src/routes/configuracoes/queries/+page.svelte — linha ~86 -->
{#each ordenadas as q}
```

(mantém o restante do `<tr>` de cada linha exatamente como está — só a fonte do `{#each}` muda de `filtradas` para `ordenadas`)

- [ ] **Step 5: Reiniciar o frontend e verificar manualmente**

```bash
docker restart datahub_frontend
```

Em `http://localhost:3000/configuracoes/queries`:
1. Clicar em "Nome" — lista ordena A→Z, aparece `▲` ao lado de "Nome".
2. Clicar em "Nome" de novo — ordena Z→A, `▲` vira `▼`.
3. Clicar em "Nome" uma terceira vez — volta à ordem original da API, sem seta.
4. Clicar em "Tipo" — ordena por tipo crescente, seta em "Tipo"; "Nome" não tem mais seta.
5. Aplicar um filtro de Tipo com "Cache TTL" ordenado — a lista filtrada continua ordenada por Cache TTL.
6. Clicar em "Ações" — nada acontece (sem cursor de ponteiro, sem reordenar).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/+page.svelte
git commit -m "feat: add sortable column headers to queries list"
```

---

## Task 3: Ordenação em `/configuracoes/variaveis`

**Files:**
- Modify: `frontend/src/routes/configuracoes/variaveis/+page.svelte`

**Interfaces:**
- Consumes: `ordenarLista`, `proximaDirecao` de `frontend/src/lib/sort.js` (Task 1)
- Produces: `ordenadas` — array renderizado na tabela, substituindo `variaveis` no `{#each}`

- [ ] **Step 1: Importar o utilitário, adicionar estado e colunas clicáveis**

```javascript
// frontend/src/routes/configuracoes/variaveis/+page.svelte — topo do <script>, linha ~1-7
import { onMount } from 'svelte';
import { api } from '$lib/api.js';
import { ordenarLista, proximaDirecao } from '$lib/sort.js';

let variaveis   = [];
let carregando  = true;
let erro        = null;
let ordenarCampo    = null;
let ordenarDirecao  = null;

const colunas = [
  { label: 'Slug',        campo: 'slug' },
  { label: 'Nome',        campo: 'nome' },
  { label: 'Tipo',        campo: 'tipo' },
  { label: 'Parâmetros',  campo: null },
  { label: 'Query Fonte', campo: 'query_fonte' },
  { label: 'Ações',       campo: null },
];

function onClickColuna(campo) {
  if (!campo) return;
  ordenarDirecao = proximaDirecao(campo, ordenarCampo, ordenarDirecao);
  ordenarCampo = ordenarDirecao ? campo : null;
}
```

- [ ] **Step 2: Adicionar a lista ordenada reativa, logo após o bloco `tipoLabel`**

```javascript
// frontend/src/routes/configuracoes/variaveis/+page.svelte — logo após `const tipoLabel = {...}`
$: ordenadas = ordenarLista(variaveis, ordenarCampo, ordenarDirecao, (item, campo) => {
  if (campo === 'query_fonte') return !!item.query_fonte;
  return item[campo];
});
```

- [ ] **Step 3: Trocar o cabeçalho estático pelo `{#each colunas as c}` clicável**

```svelte
<!-- frontend/src/routes/configuracoes/variaveis/+page.svelte — linha ~52-60, dentro de <thead> -->
<thead>
  <tr>
    {#each colunas as c}
      <th class:sortable={c.campo} on:click={() => onClickColuna(c.campo)}>
        {c.label}{#if ordenarCampo === c.campo}{ordenarDirecao === 'asc' ? ' ▲' : ' ▼'}{/if}
      </th>
    {/each}
  </tr>
</thead>
```

- [ ] **Step 4: Renderizar `ordenadas` no lugar de `variaveis`, e adicionar a classe `.sortable` no `<style>`**

```svelte
<!-- linha ~63 -->
{#each ordenadas as v}
```

```css
/* frontend/src/routes/configuracoes/variaveis/+page.svelte — dentro do <style>, junto das outras regras de th/td */
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--text); }
```

- [ ] **Step 5: Reiniciar o frontend e verificar manualmente**

```bash
docker restart datahub_frontend
```

Em `http://localhost:3000/configuracoes/variaveis`, repetir a mesma checagem de 3 estados da Task 2 (asc → desc → sem ordenação) nas colunas Slug, Nome, Tipo e Query Fonte. Confirmar que "Parâmetros" e "Ações" não reagem a clique (sem cursor de ponteiro, sem reordenar).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/configuracoes/variaveis/+page.svelte
git commit -m "feat: add sortable column headers to variaveis list"
```

---

## Task 4: Ordenação em `/configuracoes/usuarios`

**Files:**
- Modify: `frontend/src/routes/configuracoes/usuarios/+page.svelte`

**Interfaces:**
- Consumes: `ordenarLista`, `proximaDirecao` de `frontend/src/lib/sort.js` (Task 1)
- Produces: `ordenadas` — array renderizado na tabela, substituindo `usuarios` no `{#each}`

- [ ] **Step 1: Importar o utilitário, adicionar estado e colunas clicáveis**

```javascript
// frontend/src/routes/configuracoes/usuarios/+page.svelte — topo do <script>, linha ~1-7
import { onMount } from 'svelte';
import { api } from '$lib/api.js';
import { ordenarLista, proximaDirecao } from '$lib/sort.js';

let usuarios   = [];
let carregando = true;
let erro       = null;
let ordenarCampo    = null;
let ordenarDirecao  = null;

const colunas = [
  { label: 'Nome',      campo: 'nome' },
  { label: 'E-mail',    campo: 'email' },
  { label: 'Perfil',    campo: 'role' },
  { label: 'Status',    campo: 'ativo' },
  { label: 'Empresas',  campo: null },
  { label: 'Ações',     campo: null },
];

function onClickColuna(campo) {
  if (!campo) return;
  ordenarDirecao = proximaDirecao(campo, ordenarCampo, ordenarDirecao);
  ordenarCampo = ordenarDirecao ? campo : null;
}
```

- [ ] **Step 2: Adicionar a lista ordenada reativa**

```javascript
// frontend/src/routes/configuracoes/usuarios/+page.svelte — logo após onMount
$: ordenadas = ordenarLista(usuarios, ordenarCampo, ordenarDirecao);
```

- [ ] **Step 3: Trocar o cabeçalho estático pelo `{#each colunas as c}` clicável**

```svelte
<!-- frontend/src/routes/configuracoes/usuarios/+page.svelte — linha ~44-52, dentro de <thead> -->
<thead>
  <tr>
    {#each colunas as c}
      <th class:sortable={c.campo} on:click={() => onClickColuna(c.campo)}>
        {c.label}{#if ordenarCampo === c.campo}{ordenarDirecao === 'asc' ? ' ▲' : ' ▼'}{/if}
      </th>
    {/each}
  </tr>
</thead>
```

- [ ] **Step 4: Renderizar `ordenadas` no lugar de `usuarios`, e adicionar a classe `.sortable` no `<style>`**

```svelte
<!-- linha ~55 -->
{#each ordenadas as u}
```

```css
/* frontend/src/routes/configuracoes/usuarios/+page.svelte — dentro do <style>, junto das outras regras de th/td */
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--text); }
```

- [ ] **Step 5: Reiniciar o frontend e verificar manualmente**

```bash
docker restart datahub_frontend
```

Em `http://localhost:3000/configuracoes/usuarios`, repetir a checagem de 3 estados nas colunas Nome, E-mail, Perfil e Status. Confirmar que "Empresas" e "Ações" não reagem a clique. Confirmar que a linha do usuário inativo (classe `.inativo`, opacidade reduzida) continua funcionando normalmente após reordenar.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/configuracoes/usuarios/+page.svelte
git commit -m "feat: add sortable column headers to usuarios list"
```

---

## Verificação Final

- [ ] `frontend/src/lib/sort.js` criado e importado pelas 3 páginas sem erro de build
- [ ] Toggle de 3 estados (asc → desc → sem ordenação) funciona em todas as colunas clicáveis das 3 telas
- [ ] Seta ▲/▼ aparece só na coluna ativa, some no 3º clique ou ao clicar em outra coluna
- [ ] "Ações" (3 telas), "Parâmetros" (Variáveis) e "Empresas" (Usuários) não são clicáveis
- [ ] Em Queries, ordenação + filtro de Tipo funcionam juntos sem conflito
- [ ] Nenhuma chamada de API nova — comportamento existente (toggle ativo, editar, deletar/desativar) continua funcionando sem regressão nas 3 telas
