# Impressão de painel + PDF padronizado de tabelas — Design

Data: 2026-09-08
Status: aprovado (aguardando review do spec antes do plano de implementação)

## 1. Objetivo

Dar ao DataHub uma saída impressa/PDF **moderna e padronizada**, com o mesmo
cabeçalho de identidade em dois pontos de entrada:

1. **Imprimir o painel inteiro** — botão na tela do painel que abre um relatório
   com todos os indicadores daquele painel (KPIs, gráficos, tabelas, tabelas
   dinâmicas e mapa), respeitando os filtros ativos.
2. **Exportar PDF de uma tabela** (`table` e `table_dynamic`) — o botão "⬇ PDF"
   de hoje passa a gerar o relatório no mesmo padrão visual, em vez do PDF
   "cru" do jsPDF/autoTable.

O cabeçalho segue o padrão visual do projeto PsoEducare
(`C:\Users\jhonatanw\git\PsoEducare\docs\PADRAO_RELATORIOS.md` e
`docs/Exemplo Cabecalho.pdf`): faixa verde com logo em círculo branco,
subtítulo em caixa-alta, título grande, dados da empresa à direita, rodapé com
filete. **Não é reaproveitamento de código** — o PsoEducare é JasperReports/Java;
aqui reconstruímos o visual em HTML/CSS.

## 2. Decisões tomadas (brainstorming)

| Tema | Decisão |
|---|---|
| Mecanismo | **HTML/CSS + `window.print()`** ("Salvar como PDF" do browser) nos dois pontos. Sem jsPDF pra PDF. |
| Endereço/CNPJ da empresa | **Adicionar** colunas `endereco` e `cnpj` em `empresas` + campos na tela de config. |
| Layout da impressão do painel | **Preserva o grid do painel** (mesma disposição `grid-column`/`grid-row`). |
| Mapa na impressão | **Incluído.** |
| Chips de filtros ativos no cabeçalho | **Sim**, linha abaixo do título. |
| Paleta do relatório | **Sempre verde-clara do padrão**, ignora o tema (escuro/claro) do app. |
| Cores dos indicadores (KPI/chart) | **Mantidas como aparecem no painel** — sem override de cor em modo relatório. |
| Textos fixos | Subtítulo: `RELATÓRIO DE INDICADORES` (painel) / `RELAÇÃO DE DADOS` (tabela). Rodapé esquerdo: `DataHub · GPA Analytics`. Sem pill de número de documento. |
| Botão "Imprimir" | No cabeçalho da página do painel, ao lado do nome. |
| Export PDF individual | Só `table` e `table_dynamic` por enquanto. |

### Abordagem escolhida vs. alternativa

- **Escolhida — rota de relatório dedicada, nova aba.** Página própria, sem
  sidebar, tema verde-claro forçado no `:root` daquela aba. Isola do tema escuro
  do app; ECharts e KPIs herdam a paleta clara sem gambiarra; a mesma rota serve
  painel inteiro e indicador único.
- **Rejeitada — bloco escondido `@media print` na própria página do painel.**
  ECharts fixa as cores no momento do render (tela escura), o grid tem
  `overflow`, e sobram dois visuais brigando. Frágil.

### Fora de escopo (YAGNI agora)

- **Designer de posições de campo por query** (definir X/Y, largura, quebra de
  linha de cada campo, estilo "ferramenta de relatório"). É projeto futuro
  separado. Este design só evita bloqueá-lo: o modelo de posicionamento por
  `coluna/span/linha` já existe em `painel_indicadores` e serviria de precedente
  pra uma tabela filha `query_layout_campos`.
- **"Página X de Y" exato.** CSS puro não garante isso cross-browser. Fase 2 com
  paged.js se for pedido. Por ora: rodapé fixo repetido por página, sem contador
  de página (ou o do próprio diálogo de impressão do browser).
- **Endpoint backend de render HTML→PDF** (headless Chrome) pra devolver arquivo
  `.pdf` direto. Escape hatch documentado; não entra agora.

## 3. Arquitetura

```
Painel (/painel/[slug])
  ├─ botão "Imprimir"  ─────────────────►  window.open('/relatorio/painel/<slug>?<filtros>')
  └─ DataTable / DynamicTable
        └─ botão "⬇ PDF"  ──────────────►  window.open('/relatorio/painel/<slug>?indicador=<id>&<filtros>')

/relatorio/painel/[slug]  (nova rota, nova aba, SEM chrome do app)
  ├─ força paleta verde-clara no :root desta aba
  ├─ api.renderizarPainel(painelId, filtros)   (mesma chamada do painel)
  ├─ RelatorioCabecalho  (faixa verde + logo + empresa + filtros)
  ├─ corpo:
  │     ├─ modo painel     → grid completo, reusa KPICard/ChartPanel/DataTable/DynamicTable/MapPanel
  │     └─ modo indicador  → só o indicador de id=<id>, largura total, tabela sem paginação
  ├─ RelatorioRodape  (position: fixed, repete por página)
  └─ toolbar .no-print: "Imprimir / Salvar PDF" (habilita quando tudo pronto)
```

## 4. Schema

```sql
ALTER TABLE empresas ADD COLUMN endereco TEXT;
ALTER TABLE empresas ADD COLUMN cnpj     VARCHAR(20);
```

- Adicionar em `scripts/init-meta-prod.sql` (bloco `CREATE TABLE empresas`) e no
  bloco idempotente de deltas.
- Adicionar ao README em "Deltas de schema pendentes" (aplicar em produção via
  `psql -U postgres -d datahub_meta` no serviço `postgres` do EasyPanel — ver
  memória `prod-postgres-role`).
- Nota de memória após o deploy.

Sem tabelas novas. Sem FKs novas.

## 5. Backend

### 5.1 `routes/empresas.py`

- `EmpresaInput` e `EmpresaUpdate` (Pydantic): campos `endereco: str | None`,
  `cnpj: str | None`.
- `ALLOWED` / lista de colunas do UPDATE: incluir `endereco`, `cnpj`.
- INSERT de criar empresa: incluir as duas colunas.
- SELECT de `listar` e de `detalhe`: incluir `endereco`, `cnpj`.

  > Lembrete da memória (`feature: duplicar query`): ao liberar edição de um
  > campo, conferir que ele está **tanto no modelo Pydantic quanto na
  > allowlist** — as duas coisas são independentes nesse arquivo.

### 5.2 `routes/auth.py` — `GET /api/auth/me`

Hoje o `+layout.svelte` usa `me.company_name` / `me.url_impressao_base` ao montar
`empresaAtiva`. Adicionar ao payload de `/me`:

- `company_endereco`
- `company_cnpj`

(buscados no mesmo SELECT de `empresas` que já resolve o nome).

### 5.3 `renderizar_painel`

**Sem mudança.** A rota de relatório usa exatamente `api.renderizarPainel`, que
já devolve `pi.*` (inclui `pi.id`, usado pelo modo indicador único) e todos os
campos de configuração de cada indicador.

### 5.4 Testes backend

`backend/tests/test_empresas_endereco_cnpj.py` (novo):

- round-trip: criar empresa com `endereco`/`cnpj` → `GET /{id}` devolve os dois.
- update: `PUT` alterando só `endereco` → persiste, não zera `cnpj`.
- `GET /api/auth/me` inclui `company_endereco` e `company_cnpj` pra usuário com
  empresa que tem os campos preenchidos.

Limpeza: usar helpers de hard-delete do `conftest.py` se criar empresa; se não
houver helper de empresa, criar um análogo (`hard_delete_empresa`) — **não** usar
o DELETE da API se ele for soft-delete.

## 6. Frontend

### 6.1 Store `auth.js`

`empresaAtiva` passa a carregar `endereco` e `cnpj`. Popular:

- No `+layout.svelte` `onMount` (a partir de `me.company_endereco` /
  `me.company_cnpj`).
- Em qualquer outro ponto que faça `empresaAtiva.set(...)` — auditar (`/sso`,
  `selecionar-empresa`). Onde o dado não vier, `null` (cabeçalho esconde a linha).

### 6.2 Tema do relatório — `frontend/src/lib/relatorio/tema-relatorio.css`

Escopo `:root.relatorio-tema` (o `ChartPanel` lê as vars via
`getComputedStyle(document.documentElement)`, então os tokens **têm** de estar no
`<html>`, não num wrapper). A rota de relatório adiciona a classe
`relatorio-tema` em `document.documentElement` no `onMount` e remove o atributo
`data-theme` que o `+layout.svelte` possa ter setado; desfaz em `onDestroy`.
Redefine os tokens que os componentes reusados leem:

| Token | Valor relatório |
|---|---|
| `--bg` / fundo da página | `#F4F6F2` |
| `--surface` | `#FFFFFF` |
| `--surface2` | `#E9F3EC` |
| `--border` | `#E3E8E1` |
| `--text` | `#2B2B2B` |
| `--muted` (rótulo) | `#8A968A` |
| `--accent` / verde | `#2E5E3E` |
| `--accent-green` | `#4CAF50` |
| verde-escuro (base gradiente) | `#1F3D2B` |
| verde-suave (subtítulo header) | `#BFE3C6` |

- Também define `@page { size: A4; margin: 14mm 12mm; }` e o padding de topo/base
  do corpo pra não passar por baixo do cabeçalho/rodapé `position: fixed`.
- `@media print`: esconde `.no-print`; `-webkit-print-color-adjust: exact` /
  `print-color-adjust: exact` pra faixa verde e cores dos cards saírem.
- `@media screen`: mostra a página numa "folha" centralizada com sombra (preview
  agradável antes de imprimir).

> **Cores dos indicadores mantidas:** KPICard continua recebendo
> `kpi_cor_fonte`/`kpi_cor_fundo`; ChartPanel mantém sua paleta `COLORS`. O tema
> só ajusta o entorno (fundo, texto de eixo, bordas, cabeçalho de tabela).

### 6.3 `RelatorioCabecalho.svelte`

Props: `titulo`, `subtitulo`, `filtros` (`[{nome, valor}]`).

Layout (reconstrução do `docs/Exemplo Cabecalho.pdf`):

- Faixa full-bleed: `background: linear-gradient(...)` verde-escuro→verde +
  arcos decorativos em `<svg>` inline (círculos/paths com opacidade baixa),
  espelhando o `header_tema.png` do PsoEducare.
- Esquerda: círculo branco com a logo da empresa (`<img src={empresaAtiva.logo_url}>`,
  `object-fit: contain`, `on:error` esconde).
- Centro: subtítulo (caixa-alta, verde-suave, pequeno) + título grande branco.
- Direita: `empresaAtiva.nome` (bold), `empresaAtiva.endereco`,
  `empresaAtiva.cnpj` (quando houver), e `Emitido em DD/MM/AAAA às HH:MM`
  (`Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })`).
- Abaixo da faixa: se `filtros.length`, linha de chips
  `<nome>: <valor>` (mesmo visual discreto dos chips do painel, adaptado à
  paleta clara).
- `position: fixed; top: 0` — repete em toda página impressa.

### 6.4 `RelatorioRodape.svelte`

- Filete `1px` cor `--border` no topo.
- Esquerda: `DataHub · GPA Analytics`.
- Direita: `Relatório gerado eletronicamente · DD/MM/AAAA HH:MM`.
- `position: fixed; bottom: 0` — repete por página.

### 6.5 `$lib/resumoFiltros.js` (refactor)

Extrair de `frontend/src/routes/painel/[slug]/+page.svelte` a lógica reativa
`resumoFiltros` (linhas ~31-51 + `fmtData`) para um módulo puro:

```js
export function resumoFiltros(variaveis, filtrosAtivos, opcoesPorVariavel) { ... }
```

Usado pelo `+page.svelte` do painel (substitui o bloco atual) e pela rota de
relatório (pra montar os chips do cabeçalho). Sem mudança de comportamento no
painel.

### 6.6 Rota `/relatorio/painel/[slug]`

**Arquivo:** `frontend/src/routes/relatorio/painel/[slug]/+page.svelte`.

**Carve-out no `+layout.svelte` raiz:** hoje ele envolve toda rota não-pública em
`.shell` (sidebar + topbar). Adicionar branch: se
`$page.url.pathname.startsWith('/relatorio/')`, renderizar só
`<div class="relatorio">{@slot}</div>` — **mantendo** o guard de auth do
`onMount` (a rota precisa do JWT do `localStorage` pra chamar a API; token e
`empresaAtiva` são compartilhados entre abas na mesma origem).

**Fluxo da página:**

1. Lê `slug`, `indicador` (opcional) e o resto dos parâmetros (filtros) de
   `$page.url.searchParams`.
2. `onMount`: `document.documentElement.classList.add('relatorio-tema')` +
   `.removeAttribute('data-theme')`; importa `tema-relatorio.css`. `onDestroy`
   desfaz (higiene — a aba é dedicada, mas evita surpresa em navegação SPA).
3. `painel = await api.buscarPainelPorSlug(slug)`;
   `variaveis = await api.variaveisPainel(painel.id)`;
   carrega `opcoesPorVariavel` das variáveis select/multiselect (igual ao painel);
   `resultado = await api.renderizarPainel(painel.id, filtros)`.
4. `filtrosResumo = resumoFiltros(variaveis, filtros, opcoesPorVariavel)`.
5. Render:
   - `<RelatorioCabecalho titulo={painel.nome ou ind.titulo}
     subtitulo={indicador ? 'RELAÇÃO DE DADOS' : 'RELATÓRIO DE INDICADORES'}
     filtros={filtrosResumo} />`
   - **Modo painel** (`!indicador`): mesmo `<div class="painel-grid">` do
     `+page.svelte` (mesmas regras de `grid-template-columns` e
     `grid-column/grid-row` por indicador), reusando os componentes existentes.
     `break-inside: avoid` em cada `.grid-item`.
   - **Modo indicador** (`indicador` presente): acha
     `ind = resultado.indicadores.find(i => String(i.id) === indicador)`; renderiza
     só ele, largura total. Pra `table`/`table_dynamic`, passar uma prop nova
     `modoRelatorio` que:
       - desliga a paginação (renderiza todas as linhas),
       - esconde a barra de paginação/ações/export,
       - deixa `<thead>` repetir por página impressa (`display: table-header-group`),
       - permite `white-space: normal` / wrap nas células,
       - orientação: se `colunasEfetivas.length > ~8`, adicionar
         `@page { size: A4 landscape }` (classe condicional na raiz).
   - `<RelatorioRodape />`.
6. Toolbar `.no-print` fixa no topo (só em `@media screen`): estado
   `pronto` que vira `true` quando:
   - todos os `ChartPanel` sinalizaram render (evento/callback `on:pronto`, ou um
     `tick()` + pequeno timeout de fallback),
   - todos os `MapPanel` dispararam `map.whenReady` **e** os tiles visíveis
     carregaram (`map.once('load')` + contador de `tileload`/`tileerror`),
   - `document.fonts.ready` e imagens (`img.decode()`/`complete`).
   Enquanto `!pronto`: "Preparando relatório…". Quando `pronto`: botão
   **"Imprimir / Salvar PDF"** → `window.print()`. **Sem auto-print.**

### 6.7 Componentes reusados — mudanças mínimas

- **`ChartPanel.svelte`**: emitir `dispatch('pronto')` após o primeiro
  `setOption` (pro readiness da toolbar). Nenhuma mudança visual.
- **`MapPanel.svelte`**: expor readiness de tiles (evento `pronto` após
  `map` load). Garantir `invalidateSize()` depois do layout do relatório.
- **`DataTable.svelte`**: prop `modoRelatorio = false`. Quando `true`: sem
  paginação, sem `.pagination`, `<thead>` `table-header-group`, células com wrap.
  Props novas `painelSlug` e `indicadorId` (usadas fora do modo relatório, no
  botão PDF — ver 6.8).
- **`DynamicTable.svelte`**: idem `modoRelatorio` (renderiza a árvore inteira
  expandida, sem os controles) + `painelSlug`/`indicadorId`.
- **`KPICard.svelte`**: **sem mudança** (cores mantidas).

### 6.8 Ligar os pontos de entrada

**`frontend/src/routes/painel/[slug]/+page.svelte`:**

- `.painel-header`: botão "Imprimir" ao lado do `<h2>`:
  ```js
  function imprimirPainel() {
    const p = new URLSearchParams(filtrosAtivos);
    window.open(`/relatorio/painel/${slug}?${p}`, '_blank', 'noopener');
  }
  ```
- Passar `painelSlug={slug}` e `indicadorId={ind.id}` para `<DataTable>` e
  `<DynamicTable>`.
- Trocar o uso do bloco `resumoFiltros` local pelo import de `$lib/resumoFiltros.js`.

**`DataTable.svelte` / `DynamicTable.svelte`:**

- Botão "⬇ PDF": em vez de `baixarPDF(...)`, abrir a rota de relatório:
  ```js
  function exportarPDF() {
    const p = new URLSearchParams(/* filtros herdados via prop ou window.location */);
    p.set('indicador', indicadorId);
    window.open(`/relatorio/painel/${painelSlug}?${p}`, '_blank', 'noopener');
  }
  ```
  Os filtros ativos: passar do `+page.svelte` uma prop `filtrosQuery` (string ou
  objeto) pra não depender de `window.location`.
- CSV e Excel: **inalterados**.

**`frontend/src/lib/exportTable.js`:**

- Remover `baixarPDF`, `baixarPDFAgrupado`, `prepararDocumentoPDF`,
  `desenharCabecalhoPagina`, `numerarPaginasPDF`, `salvarPDF`, `logoParaDataURL`.
- Remover imports `jspdf` e `jspdf-autotable`.
- Remover `jspdf` / `jspdf-autotable` do `package.json` (conferir que nada mais
  usa).

### 6.9 Config de empresa — `/configuracoes/empresas/[id]` e `/nova`

Dois campos de texto novos: "Endereço" (linha única, vira a linha de endereço do
cabeçalho) e "CNPJ". Opcionais. Enviados no payload de criar/editar empresa.

## 7. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Tiles do mapa não carregam antes do print → mapa em branco | Readiness explícito (tileload/load) antes de habilitar o botão; sem auto-print. |
| ECharts canvas não imprime bem | Já usa `renderer: 'svg'` — ok. |
| Cabeçalho/rodapé `position: fixed` sobrepõem conteúdo | `@page` margin + padding de topo/base no corpo calibrados; testar em Chrome e Edge. |
| Browser adiciona seu próprio cabeçalho/rodapé (URL, data) | Documentar "desmarcar Cabeçalhos e rodapés" no diálogo; ou aceitar. |
| Cores de fundo não saem na impressão | `print-color-adjust: exact` + instrução "ativar Gráficos de segundo plano". |
| KPI com `kpi_cor_fundo` escuro sobre relatório claro | Decisão do usuário: manter. Sem ação. |
| Tabela muito larga (muitas colunas) | Landscape automático + wrap de célula. Fidelidade fina fica pro designer futuro (fora de escopo). |
| `+layout.svelte` carve-out quebrar auth da rota | Manter o `onMount` de auth rodando; só troca o markup do `{:else}`. |

## 8. Plano de deploy

1. Merge em `master`.
2. Aplicar delta em produção:
   `ALTER TABLE empresas ADD COLUMN endereco TEXT; ALTER TABLE empresas ADD COLUMN cnpj VARCHAR(20);`
   via `psql -U postgres -d datahub_meta` no serviço `postgres` do EasyPanel.
3. Deploy backend + frontend no EasyPanel. Se não refletir: "Forçar
   reconstrução"; se ainda não, Stop → Start (ver armadilhas de deploy na
   memória do projeto).
4. Preencher `endereco`/`cnpj` das empresas reais (`prats`, `vitoria-agronegocios`)
   pela tela de config.
5. Verificar em produção: abrir um painel, "Imprimir", conferir cabeçalho.
6. Nota de memória: schema sincronizado + nova feature.

## 9. Verificação (antes de "pronto")

- `docker exec datahub_backend python -m pytest tests/ -v` — verde, incluindo o
  arquivo novo.
- `docker restart datahub_frontend` após cada edição em `frontend/src/`
  (armadilha do watcher no Windows — memória do projeto).
- Playwright manual (`admin@datahub.local` / `admin123`, empresa `prats`):
  - `/painel/lanc_fichas` → botão "Imprimir" → nova aba `/relatorio/painel/...`
    abre, cabeçalho com nome + endereço da empresa, chips dos filtros ativos,
    todos os indicadores renderizados, rodapé presente.
  - Tabela → "⬇ PDF" → abre relatório só daquela tabela, todas as linhas, sem
    paginação.
  - Screenshot de ambos anexado pro usuário.
- Conferir `@media print` via preview de impressão do Chrome (não só a tela).
