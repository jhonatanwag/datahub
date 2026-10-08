# Apresentação de Painéis — Design

Data: 2026-10-08

## Objetivo

Permitir cadastrar **apresentações**: sequências de painéis (slides) que rodam sozinhas em tela cheia numa TV, sem intervenção. Cada slide é um **painel já existente**, com filtros fixos e tempo de exibição próprios. A apresentação atualiza os dados periodicamente e rola automaticamente os slides mais altos que a tela.

## Decisões acordadas

- Slide = referência a um painel existente (`paineis`). O mesmo painel pode ser usado no menu e em várias apresentações. Nada muda em `paineis`.
- Filtros fixos ficam no slide (não no painel). Ao adicionar o painel, começam com o `valor_padrao` das variáveis dele, **guardados como tokens crus** (`hoje`, `mes_atual_inicio`…) e resolvidos a cada atualização, para uma TV ligada por dias não ficar com a data antiga. Só o que o usuário edita no preparo/execução vira valor fixo (override, não gravado).
- Permissão: `empresa_id` (NULL = todas) + usuários com acesso; só admin cadastra. Admin enxerga e executa todas as apresentações ativas da empresa, sem precisar de vínculo. Usuários `externo` (SSO) não têm acesso (403) e o item some do menu.
- Sessão da TV: renovação automática do token enquanto a apresentação está aberta (sem link de TV sem login).
- Rolagem automática quando o slide excede a altura da tela.

## 1. Dados e API

### Tabelas (delta SQL em `backend/sql/`)

- `apresentacoes`: `id`, `slug` (UNIQUE, usa `_`), `nome`, `descricao`, `empresa_id` (NULL = todas), `intervalo_atualizacao_seg` (padrão 300), `ativo`, `criado_em`, `atualizado_em` (trigger `update_atualizado_em`).
- `apresentacao_slides`: `id`, `apresentacao_id` (FK, ON DELETE CASCADE), `painel_id` (FK `paineis`), `ordem`, `duracao_seg`, `filtros` (JSONB: valores por parâmetro).
- `apresentacao_usuarios`: `apresentacao_id`, `usuario_id` (PK composta, CASCADE), igual a `painel_usuarios`.

### API (`backend/routes/apresentacoes.py`)

- Admin: CRUD de apresentações; CRUD e reordenação de slides; `GET/PUT /{id}/usuarios`.
- Usuário: `GET /minhas` (alimenta o menu; filtrada por usuário e empresa); `GET /{id}/executar` (slides em ordem, filtros, durações, intervalo de atualização).
- Dados dos slides: reaproveita `GET /api/paineis/{painel_id}/renderizar` e o endpoint de variáveis, **sem alteração em `routes/paineis.py`** (o `renderizar` não checa `painel_usuarios` para usuários internos).
- `POST /api/auth/renovar`: devolve token novo se o atual for válido; respeita a blacklist de logout.

## 2. Tela de execução

- Rotas: `/apresentar` (lista as apresentações do usuário) e `/apresentar/[id]`. Menu "Apresentar painéis" logo abaixo de Dashboard (`navLinks` em `+layout.svelte`).
- **Preparo:** mostra os slides com os filtros fixos, editáveis só nesta execução (não grava). Botão "Iniciar" entra em tela cheia (exige clique do usuário; não inicia sozinha por URL).
- **Rodando:** layout sem menu lateral/cabeçalho (rota especial, como `/relatorio/`). Cada slide fica pelo tempo configurado; do último volta ao primeiro (loop).
- **Rolagem automática:** slide mais alto que a tela rola de forma contínua e suave até o fim, com pausa curta no topo e no fim. A duração configurada é o mínimo: o slide fica o tempo necessário para a rolagem terminar. Velocidade calculada para o percurso caber na duração (descontadas as pausas), com **teto** de 80 px/s para manter legibilidade; se o teto impedir, o slide se estende.
- **Atualização de dados:** a cada `intervalo_atualizacao_seg`, refaz as consultas do slide atual em segundo plano, trocando os dados sem piscar e sem perder a posição de rolagem. Os outros slides carregam quando chegam a vez.
- **Token:** renovação a cada ~30 min.
- **Falhas:** mantém os dados antigos, mostra aviso discreto ("Sem atualizar desde HH:MM") e tenta no próximo ciclo. Nunca tela em branco nem redirecionamento para login por erro passageiro de rede ou de consulta.
- **Controles:** botão pequeno no canto, que some após alguns segundos sem movimento do mouse. Abre barra com: sair (sai da tela cheia e volta à lista), pausar/continuar, anterior/próximo, filtros do slide atual (ao aplicar, refaz a consulta daquele slide) e indicador "Slide N de M".
- **Reuso:** extrair de `painel/[slug]/+page.svelte` (503 linhas) o componente que desenha o grid de indicadores (gráfico, KPI, tabela, card, mapa) para uso compartilhado, sem alterar o comportamento do painel normal.

## 3. Cadastro (admin), testes e deploy

### Cadastro

- Item "Apresentações" em `adminLinks`. `/configuracoes/apresentacoes` (lista: busca, ativo/inativo), `/nova` e `/[id]`.
- Três blocos: (1) dados (nome, slug, descrição, empresa, intervalo de atualização em minutos); (2) slides, lista ordenável com painel (select), tempo em segundos e filtros fixos via `FiltroVariavel` com as variáveis do painel escolhido, mais "Adicionar slide"; (3) usuários com acesso, mesmo seletor da tela de painéis.
- Painéis inativos ou apagados dentro de uma apresentação aparecem sinalizados no cadastro; a execução os pula.

### Casos de borda

- Apresentação sem slides: "Nenhum slide cadastrado".
- Usuário com acesso à apresentação, mas não ao painel individual: vê o slide (o `renderizar` não restringe usuários internos).
- Tela cheia exige clique do usuário; a apresentação não inicia sozinha por URL. A tela também pede wake lock (quando o navegador suporta) para a TV não apagar.

### Testes

- Backend (pytest): CRUD e permissões, `minhas` por usuário e empresa, `executar`, acesso ao `renderizar` via apresentação, `auth/renovar` (inclui token na blacklist).
- Frontend (vitest): lógica pura em `lib/apresentacao.js` (velocidade da rolagem, tempo efetivo do slide, ordem de avanço).
- Tela cheia, rolagem e troca de slides: verificação manual no navegador; o navegador de teste trava com gráficos e modal, então o que não for verificável lá será informado explicitamente.

### Deploy

- Delta SQL das três tabelas **antes** do deploy, em prod e teste. Sem mudança no `pdf-renderer` nem no Swarm.
- README ganha seção curta sobre apresentações.

## Fora do escopo

- Link de TV sem login que sobrevive a reinício.
- Transições animadas entre slides.
- Montar o layout de um slide sem passar por um painel.
