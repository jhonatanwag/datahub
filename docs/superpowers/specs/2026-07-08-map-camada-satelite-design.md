# Camada de mapa (padrão / satélite) para queries tipo `map` — Design

## Contexto

O tipo de query `map` já existe (`docs/superpowers/plans/2026-06-27-map-query-type.md`, implementado). Hoje `MapPanel.svelte` escolhe as tiles com base apenas no tema do usuário (claro/escuro, via CartoDB), sem opção de visão de satélite. O pedido: permitir configurar, na tela de cadastro/edição de query (`/configuracoes/queries/nova` e `/configuracoes/queries/[id]`), que um mapa use uma camada de satélite — para dar mais contexto visual da área (relevo, construções, vegetação) do que o mapa vetorial atual permite.

## Decisões

- **Onde a escolha mora:** nos dois lugares. A query define a camada **padrão** (persistida no banco); quem está vendo o painel pode alternar para a outra camada em tempo real, sem persistir a escolha.
- **Provedor de satélite:** Esri World Imagery — gratuito, sem API key/conta, mesmo padrão de "sem custo" que o CartoDB já usado.
- **Rótulos sobre o satélite:** não. Só a imagem aérea pura, sem overlay de nomes de rua/cidade (mantém a implementação simples; pode ser adicionado depois se fizer falta).

## Modelo de dados

Nova coluna na tabela `queries`:

```sql
ALTER TABLE queries ADD COLUMN mapa_camada VARCHAR(20) DEFAULT 'padrao';
```

Valores válidos: `'padrao'` (comportamento atual — tema claro/escuro via CartoDB) ou `'satelite'` (Esri World Imagery). Só é relevante quando `tipo = 'map'`, mas a coluna existe para todas as linhas (mesmo padrão de `kpi_cor_fonte`/`kpi_cor_fundo`, que existem mas só são usadas quando `tipo = 'kpi'`).

**Migração:** o projeto não tem sistema de migrations — colunas novas em `queries` historicamente são adicionadas via `ALTER TABLE` manual (`docker exec` no Postgres de dev) e depois refletidas nos scripts de schema:
- `scripts/init-db.sql` — seed local de dev (alpha/beta/gamma)
- `scripts/init-meta-prod.sql` — schema de produção (datahub_meta no EasyPanel)

Ambos precisam do `mapa_camada` adicionado na definição de `CREATE TABLE queries`. Aplicar o `ALTER TABLE` no Postgres real de produção (VPS) é um passo manual, fora do escopo deste trabalho — só fica documentado como pendência de deploy.

## Backend

### `backend/routes/queries.py`

- `QueryInput`: adicionar `mapa_camada: Optional[str] = 'padrao'`.
- `QueryUpdate`: adicionar `mapa_camada: Optional[str] = None`.
- Validação em `criar_query` e `atualizar_query`: se o valor informado não estiver em `{'padrao', 'satelite'}`, retornar 400 (mesmo padrão de erro usado para `TIPOS_VALIDOS`).
- Incluir `mapa_camada` no `INSERT` de `criar_query`.
- Incluir `mapa_camada` em `ALLOWED_COLS` de `atualizar_query`.

### `backend/routes/paineis.py`

- `renderizar_painel` (linha ~294): incluir `q.mapa_camada` no `SELECT` que já traz `q.kpi_cor_fonte, q.kpi_cor_fundo`, para que o valor chegue até o payload consumido pelo frontend do painel.

## Frontend — Cadastro/edição de query

`frontend/src/routes/configuracoes/queries/nova/+page.svelte` e `.../[id]/+page.svelte`:

- `form`: adicionar `mapa_camada: 'padrao'` (nova) / carregar de `q.mapa_camada || 'padrao'` (edição).
- Novo bloco condicional `{#if form.tipo === 'map'}`, no mesmo estilo visual do bloco `{#if form.tipo === 'kpi'}` (cores do KPI):
  ```svelte
  <div class="section-block">
    <span class="section-title">Camada do Mapa</span>
    <label class="lbl">
      <select bind:value={form.mapa_camada}>
        <option value="padrao">Padrão (tema claro/escuro)</option>
        <option value="satelite">Satélite</option>
      </select>
    </label>
  </div>
  ```
- Incluir `mapa_camada` no payload enviado por `criarQuery`/`atualizarQuery`.

## Frontend — `MapPanel.svelte`

- Nova prop `export let camada = 'padrao';` (valor vindo de `ind.mapa_camada` no painel).
- Novo tile source satélite (Esri World Imagery, sem chave):
  ```js
  const TILE_URLS = {
    escuro:   'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    claro:    'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    satelite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  };
  ```
  Nota: a URL do Esri usa ordem `{z}/{y}/{x}` (não `{z}/{x}/{y}` como CartoDB) — o Leaflet resolve isso normalmente por template string, sem lógica extra.
- Estado interno `camadaAtiva`, inicializado a partir da prop `camada` no `onMount`.
- `aplicarTileLayer` passa a escolher a URL por `camadaAtiva === 'satelite' ? TILE_URLS.satelite : TILE_URLS[tema]` — ou seja, quando a camada ativa é satélite, o tema claro/escuro do usuário é ignorado para fins de tile (mas o marcador (`MARKER_STROKE`) continua respeitando o tema, já que isso não depende da camada de fundo).
- Botão de alternância sobreposto ao mapa (canto superior direito, estilo simples consistente com o resto da UI — não é um controle nativo do Leaflet, só um `<button>` posicionado absoluto sobre o container): alterna `camadaAtiva` entre `'padrao'` e `'satelite'` e re-chama `aplicarTileLayer` + `renderPontos`. Essa alternância é só local ao componente — não grava nada, não emite evento para o pai.

## Frontend — `/painel/[slug]/+page.svelte`

- Passar `camada={ind.mapa_camada}` para `<MapPanel pontos={ind.dados ?? []} camada={ind.mapa_camada} />`.

## Fora de escopo

- Rótulos de rua/cidade sobrepostos ao satélite (overlay híbrido).
- Outros provedores de satélite (Mapbox, Google, HERE).
- Aplicar o `ALTER TABLE` no Postgres de produção (VPS) — fica documentado como pendência manual de deploy, não executado aqui.
- Persistir a escolha de alternância feita em tempo de visualização (é sempre só da sessão local).

## Verificação

- Criar/editar query tipo `map` com camada `satelite` — salva e recarrega corretamente.
- `PATCH` com `mapa_camada` inválido (ex.: `"xyz"`) retorna 400.
- Painel com query `mapa_camada = 'satelite'` — abre já mostrando imagem de satélite (Esri), sem depender do tema do usuário.
- Painel com query `mapa_camada = 'padrao'` — comportamento idêntico ao atual (CartoDB claro/escuro conforme tema).
- Botão de alternância no mapa — troca a camada visualmente sem recarregar a página, nos dois sentidos (padrão→satélite e satélite→padrão).
- KPI, charts e demais tipos de query — não afetados.
