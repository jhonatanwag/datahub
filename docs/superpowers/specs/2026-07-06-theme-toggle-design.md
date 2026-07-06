# Design: Alternância de tema claro/escuro

**Data:** 2026-07-06

## Problema

O painel hoje só tem um tema (escuro fixo, definido em `frontend/src/app.css`). Alguns
usuários preferem um tema claro. É preciso oferecer a opção de trocar de tema, com a
escolha persistindo entre logins (inclusive em outro navegador/dispositivo).

## Visão geral

- A preferência de tema é uma propriedade da conta do usuário, salva no banco
  (não em `localStorage` do navegador) — assim acompanha o usuário em qualquer
  dispositivo.
- O tema é aplicado via um atributo `data-theme` na tag `<html>`, com um bloco de
  variáveis CSS alternativo em `app.css`. Todo o app já usa variáveis CSS
  (`--bg`, `--surface`, `--text`, etc.), então a maior parte da UI se adapta sem
  mudanças adicionais.
- Um botão de alternância (ícone sol/lua) fica na topbar, sempre visível.
- Apenas dois temas: **claro** e **escuro** (sem opção "seguir sistema").

## Backend

### Schema

Adicionar coluna `tema` à tabela `usuarios`:

```sql
ALTER TABLE usuarios ADD COLUMN tema VARCHAR(10) NOT NULL DEFAULT 'escuro';
```

- Rodar esse `ALTER TABLE` no container Postgres de dev já existente.
- Atualizar `scripts/init-db.sql` (definição de `CREATE TABLE usuarios`) para incluir
  `tema VARCHAR(10) NOT NULL DEFAULT 'escuro'`, para que novas instalações já nasçam
  com a coluna.
- Valores válidos: `'claro'` e `'escuro'`. Default `'escuro'` preserva o comportamento
  atual para usuários existentes.

### `middleware/auth.py`

`get_current_user` já faz um `SELECT` fresco no banco em toda requisição autenticada
(linhas 35-42 hoje). Adicionar `u.tema` a esse `SELECT`. Isso torna `tema` disponível
automaticamente em `GET /api/auth/me` e em qualquer rota que dependa de
`get_current_user`, sem precisar tocar no JWT (que continua sem carregar `tema`).

### Novo endpoint: `PUT /api/auth/tema`

Em `routes/auth.py`:

- Body: `{ "tema": "claro" | "escuro" }` (Pydantic model, validar contra os dois
  valores possíveis, rejeitar qualquer outro com 422).
- Protegido por `Depends(get_current_user)` — **sem** exigir admin, qualquer usuário
  autenticado pode trocar seu próprio tema.
- `UPDATE usuarios SET tema = $1 WHERE id = $2` usando o `id` do usuário autenticado.
- Retorna `{ "tema": "claro" }` (ou o valor salvo).

## Frontend

### Aplicação do tema

- A store `usuario` (`frontend/src/lib/stores/auth.js`) já é sincronizada com
  `localStorage` e já vai carregar `tema` junto, pois vem do `/me` (nenhuma mudança
  necessária nessa store).
- Em `frontend/src/routes/+layout.svelte`, um bloco reativo aplica o atributo:
  ```js
  $: if (typeof document !== 'undefined' && $usuario?.tema) {
    document.documentElement.setAttribute('data-theme', $usuario.tema);
  }
  ```
- Antes do login (rotas públicas `/login`, `/selecionar-empresa`, sem `usuario`
  carregado), o app permanece no tema escuro atual (nenhum atributo é setado, e o
  bloco `:root` sem seletor de atributo já é o escuro).
- **Trade-off aceito:** pode haver um flash rápido (escuro → claro) no primeiro
  carregamento após o login, até o `/me` resolver e o atributo ser aplicado. Ocorre
  uma vez por sessão de login; não justifica complexidade extra (ex: cookie de SSR)
  para este projeto.

### Paleta clara (`frontend/src/app.css`)

Novo bloco `:root[data-theme="claro"]` sobrescrevendo as variáveis existentes:

```css
:root[data-theme="claro"] {
  --bg:           #ffffff;
  --surface:      #f6f8fa;
  --surface2:     #eaeef2;
  --border:       #d0d7de;
  --text:         #1f2328;
  --muted:        #656d76;
  --accent:       #bc4c00;
  --accent-blue:  #0969da;
  --accent-green: #1a7f37;
  --danger:       #cf222e;
  --accent-purple:#8250df;
  --accent-orange:#9a6700;
}
```

`--font-display`, `--font-body`, `--radius`, `--radius-lg` não mudam entre temas.

Os poucos lugares com hex hardcoded que duplicam `.btn-primary` inline
(`+layout.svelte:440`, `configuracoes/queries/+page.svelte:62`,
`configuracoes/empresas/+page.svelte:100` — todos usando `#0d1117` como cor de texto
sobre `var(--accent)`) ficam fora de escopo: são texto escuro sobre um botão de
destaque, contraste aceitável nos dois temas, não bloqueiam a feature.

### Botão de alternância (topbar)

Em `frontend/src/routes/+layout.svelte`, ao lado de `.topbar-user`:

- Ícone sol (tema escuro ativo → oferece trocar pra claro) / lua (tema claro ativo →
  oferece trocar pra escuro), seguindo o padrão de ícones SVG inline já usado no
  arquivo (objeto `I` + função `svg()`).
- `on:click`: calcula `novoTema = $usuario.tema === 'claro' ? 'escuro' : 'claro'`,
  chama `PUT /api/auth/tema`, e em caso de sucesso atualiza a store localmente
  (`usuario.update(u => ({ ...u, tema: novoTema }))`) — aplica na hora, sem esperar
  reload. Erro de rede: mantém tema atual, sem alteração (sem toast/erro visual
  necessário para essa ação de baixo risco).

### `ChartPanel.svelte`

Cores de eixo/legenda/gridline hoje hardcoded (`#e6edf3`, `#7d8590`, `#21262d`).
Substituir por leitura das variáveis CSS computadas (`--text`, `--muted`, `--border`)
via `getComputedStyle(document.documentElement)` no momento de montar/atualizar o
gráfico, reagindo a mudanças em `$usuario.tema` (recriar a `option` do ECharts quando
o tema mudar, igual já acontece quando `dados` muda). As cores de série (`COLORS`:
azul/laranja/verde/roxo) permanecem as mesmas — funcionam em ambos os fundos.

### `MapPanel.svelte`

- Tile layer do Leaflet alterna entre `dark_all` (tema escuro, atual) e `light_all`
  (tema claro), ambos da CartoDB, conforme `$usuario.tema`.
- Cor de contorno (`color`) do `circleMarker` muda de `#0d1117` (contorno escuro,
  usado no tile escuro) para `#ffffff` (contorno claro, usado no tile claro).
  `fillColor` (`#79c0ff`, azul de destaque) permanece igual nos dois temas.
- Ao trocar o tema, o tile layer precisa ser recriado (remover o layer atual e
  adicionar o novo) — Leaflet não atualiza a URL de um tile layer existente.

## Fora de escopo

- Opção "seguir tema do sistema operacional" (`prefers-color-scheme`) — só claro e
  escuro, escolha manual.
- Página de perfil pessoal — o botão fica só na topbar.
- Cores customizáveis por KPI (`kpi_cor_fonte`/`kpi_cor_fundo`) — são configuração
  por query, já existentes, não fazem parte do tema do app.

## Testes / verificação

- Backend: testar `PUT /api/auth/tema` com valor válido (200, persiste no banco),
  valor inválido (422), sem autenticação (401).
- Frontend: login → alternar tema → recarregar página → tema permanece (confirma
  persistência via banco/`/me`). Logout e login com outro usuário → tema não vaza
  entre contas.
- Conferir visualmente: sidebar, topbar, cards, formulários, dashboard com
  KPI/gráfico/mapa nos dois temas.
