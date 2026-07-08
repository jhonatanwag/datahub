# Map Query Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o tipo `map` ao sistema de queries, permitindo consultas SQL com colunas `lat`, `lng`, `valor`, `label` que renderizam um mapa interativo com marcadores circulares proporcionais nos painéis.

**Architecture:** O tipo `map` segue o mesmo padrão dos outros tipos existentes (kpi, chart_*, table): o backend valida e executa o SQL, retorna os dados, e o frontend escolhe o componente de renderização com base em `query_tipo`. O `MapPanel.svelte` já existe com Leaflet; as mudanças são puro wiring: adicionar `map` à lista de tipos válidos no backend, ao contrato de colunas no `QueryEditor`, e ao branch de renderização no painel.

**Tech Stack:** SvelteKit (JS puro, Svelte 5), FastAPI/Python, Leaflet (já instalado via `MapPanel.svelte`)

## Global Constraints

- JS puro — sem TypeScript
- Svelte 5 compatible — sem `$:` deprecated em componentes novos (mas os arquivos existentes já usam `$:`, manter padrão)
- Contrato SQL do tipo `map`: colunas obrigatórias `lat`, `lng`, `valor`, `label`
- Sem migration de banco — `tipo` é coluna text, validação só no backend Python
- Backend roda em Docker: `datahub_backend`; frontend: `datahub_frontend`
- Após editar `.svelte` ou `.py`: `docker restart datahub_backend datahub_frontend`

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `backend/routes/queries.py` | Modificar | Adicionar `'map'` a `TIPOS_VALIDOS` |
| `frontend/src/lib/components/QueryEditor.svelte` | Modificar | Adicionar contrato `map: ['lat', 'lng', 'valor', 'label']` |
| `frontend/src/lib/components/MapPanel.svelte` | Modificar | Auto-fit bounds nos markers ao invés de view fixa |
| `frontend/src/routes/configuracoes/queries/nova/+page.svelte` | Modificar | Adicionar `'map'` ao array `tipos` |
| `frontend/src/routes/configuracoes/queries/[id]/+page.svelte` | Modificar | Adicionar `'map'` ao array `tipos` |
| `frontend/src/routes/painel/[slug]/+page.svelte` | Modificar | Importar `MapPanel`, adicionar branch `query_tipo === 'map'` |

---

## Task 1: Backend — Habilitar tipo `map`

**Files:**
- Modify: `backend/routes/queries.py:47-51`

**Interfaces:**
- Produces: `TIPOS_VALIDOS` contém `'map'` — o backend aceita criar/atualizar queries com `tipo = 'map'`

- [ ] **Step 1: Abrir o arquivo e localizar `TIPOS_VALIDOS`**

```python
# backend/routes/queries.py — linha ~47
TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context'
}
```

- [ ] **Step 2: Adicionar `'map'` ao conjunto**

```python
TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map'
}
```

- [ ] **Step 3: Reiniciar o backend e verificar**

```bash
docker restart datahub_backend
```

Abrir `http://localhost:3001/docs` (Swagger), localizar `POST /api/queries`, enviar `"tipo": "map"` — deve aceitar sem erro 400. Com qualquer outro tipo inválido (ex: `"tipo": "xyz"`) deve retornar 400.

- [ ] **Step 4: Commit**

```bash
git add backend/routes/queries.py
git commit -m "feat: add map to TIPOS_VALIDOS in queries backend"
```

---

## Task 2: QueryEditor — Contrato de colunas para tipo `map`

**Files:**
- Modify: `frontend/src/lib/components/QueryEditor.svelte:12-20`

**Interfaces:**
- Consumes: `tipo` prop passado pelo formulário de nova/editar query
- Produces: quando `tipo === 'map'`, o editor exige e valida as colunas `lat`, `lng`, `valor`, `label` no resultado do teste — igual ao comportamento dos outros tipos

- [ ] **Step 1: Localizar o objeto `contratos` no `QueryEditor.svelte`**

```javascript
// frontend/src/lib/components/QueryEditor.svelte — linha ~12
const contratos = {
  kpi:                  ['valor', 'label'],
  chart_line:           ['label', 'valor'],
  chart_bar:            ['label', 'valor'],
  chart_bar_horizontal: ['label', 'valor'],
  chart_doughnut:       ['label', 'valor'],
  table:                [],
  rag_context:          [],
};
```

- [ ] **Step 2: Adicionar entrada para `map`**

```javascript
const contratos = {
  kpi:                  ['valor', 'label'],
  chart_line:           ['label', 'valor'],
  chart_bar:            ['label', 'valor'],
  chart_bar_horizontal: ['label', 'valor'],
  chart_doughnut:       ['label', 'valor'],
  table:                [],
  rag_context:          [],
  map:                  ['lat', 'lng', 'valor', 'label'],
};
```

- [ ] **Step 3: Reiniciar frontend e verificar no formulário**

```bash
docker restart datahub_frontend
```

Ir em `http://localhost:3000/configuracoes/queries/nova`, selecionar tipo `map` (ainda não aparece — será adicionado na Task 4), colar um SQL como:

```sql
SELECT -23.5 AS lat, -46.6 AS lng, 100 AS valor, 'SP' AS label
```

Após testar: deve aparecer `✓ Contrato OK`. Se usar SQL sem a coluna `lng`, deve aparecer `⚠ Colunas obrigatórias faltando: lng`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/QueryEditor.svelte
git commit -m "feat: add map contract (lat, lng, valor, label) to QueryEditor"
```

---

## Task 3: MapPanel — Auto-fit nos bounds dos markers

**Files:**
- Modify: `frontend/src/lib/components/MapPanel.svelte`

**Interfaces:**
- Consumes: `pontos = [{lat, lng, valor, label}]`
- Produces: mapa Leaflet que ajusta zoom/centro automaticamente para caber todos os pontos ao renderizar; fallback para Brasil quando não há pontos

- [ ] **Step 1: Ler o arquivo atual**

```javascript
// frontend/src/lib/components/MapPanel.svelte — estado atual
map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);
```

E a função `renderPontos`:
```javascript
function renderPontos(L) {
  markers.forEach(m => m.remove());
  markers = [];
  if (!pontos.length) return;
  const maxVal = Math.max(...pontos.map(p => p.valor), 1);
  pontos.forEach(p => {
    const r = 8 + (p.valor / maxVal) * 22;
    const m = L.circleMarker([p.lat, p.lng], {
      radius: r, fillColor: '#79c0ff', color: '#0d1117',
      fillOpacity: .75, weight: 1.5
    }).bindPopup(`<b>${p.label}</b><br>${p.valor}`).addTo(map);
    markers.push(m);
  });
}
```

- [ ] **Step 2: Substituir `renderPontos` para usar `fitBounds`**

A mudança: após adicionar todos os markers, criar um `FeatureGroup` temporário para pegar os bounds e chamar `map.fitBounds`. Quando não há pontos, voltar ao centro do Brasil.

```javascript
function renderPontos(L) {
  markers.forEach(m => m.remove());
  markers = [];
  if (!pontos.length) {
    map.setView([-15.8, -47.9], 4);
    return;
  }
  const maxVal = Math.max(...pontos.map(p => Number(p.valor) || 0), 1);
  pontos.forEach(p => {
    const r = 8 + ((Number(p.valor) || 0) / maxVal) * 22;
    const m = L.circleMarker([p.lat, p.lng], {
      radius: r, fillColor: '#79c0ff', color: '#0d1117',
      fillOpacity: .75, weight: 1.5
    }).bindPopup(`<b>${p.label}</b><br>${p.valor}`).addTo(map);
    markers.push(m);
  });
  const group = L.featureGroup(markers);
  map.fitBounds(group.getBounds(), { padding: [32, 32] });
}
```

- [ ] **Step 3: Reiniciar frontend e verificar**

```bash
docker restart datahub_frontend
```

Verificação manual: abrir qualquer painel que já use `map` (ou criar um temporariamente), confirmar que o mapa ajusta o zoom para os pontos. Com pontos todos no estado de SP, o mapa deve mostrar SP centralizado — não o Brasil inteiro.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/MapPanel.svelte
git commit -m "feat: auto-fit map bounds to markers on load"
```

---

## Task 4: Formulários de Query — Expor tipo `map` na UI

**Files:**
- Modify: `frontend/src/routes/configuracoes/queries/nova/+page.svelte:23-27`
- Modify: `frontend/src/routes/configuracoes/queries/[id]/+page.svelte:27-31`

**Interfaces:**
- Produces: o select de tipo nos formulários de criar/editar query lista `map` como opção; ao selecionar, nenhum bloco de configuração extra é exibido (diferente de `kpi` que mostra as cores)

- [ ] **Step 1: Editar `nova/+page.svelte` — adicionar `'map'` ao array `tipos`**

```javascript
// linha ~23
const tipos = [
  'kpi', 'chart_line', 'chart_bar',
  'chart_bar_horizontal', 'chart_doughnut',
  'table', 'rag_context', 'map'
];
```

- [ ] **Step 2: Editar `[id]/+page.svelte` — mesmo change**

```javascript
// linha ~27
const tipos = [
  'kpi', 'chart_line', 'chart_bar',
  'chart_bar_horizontal', 'chart_doughnut',
  'table', 'rag_context', 'map'
];
```

- [ ] **Step 3: Reiniciar frontend e verificar**

```bash
docker restart datahub_frontend
```

Abrir `http://localhost:3000/configuracoes/queries/nova`, confirmar que o select de tipo mostra `map`. Selecionar `map` — o bloco de "Cores do KPI" **não deve aparecer** (o `{#if form.tipo === 'kpi'}` já garante isso). 

- [ ] **Step 4: Testar o fluxo completo de criação**

No formulário nova query:
1. Slug: `teste_mapa`, Nome: `Teste Mapa`, Tipo: `map`
2. SQL:
```sql
SELECT
  -23.55 AS lat, -46.63 AS lng, 500  AS valor, 'São Paulo'     AS label
UNION ALL SELECT
  -22.90, -43.17, 300, 'Rio de Janeiro'
UNION ALL SELECT
  -19.92, -43.94, 150, 'Belo Horizonte'
```
3. Clicar "Testar Query" — deve mostrar `✓ Contrato OK` e amostra com 3 linhas
4. Clicar "Salvar Query" — deve redirecionar para a lista

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/configuracoes/queries/nova/+page.svelte
git add frontend/src/routes/configuracoes/queries/[id]/+page.svelte
git commit -m "feat: expose map type in query create/edit forms"
```

---

## Task 5: Painel — Renderizar MapPanel para tipo `map`

**Files:**
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `ind.query_tipo === 'map'` e `ind.dados = [{lat, lng, valor, label}, ...]` vindos de `renderizar_painel`
- Produces: indicadores do tipo `map` renderizam `MapPanel` com os pontos da query; tipos inexistentes continuam mostrando a mensagem "Tipo X não suportado"

- [ ] **Step 1: Adicionar import de `MapPanel` no topo do script**

Localizar os imports existentes (linhas ~5-8):
```javascript
import KPICard       from '$lib/components/KPICard.svelte';
import ChartPanel    from '$lib/components/ChartPanel.svelte';
import DataTable     from '$lib/components/DataTable.svelte';
import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
```

Adicionar `MapPanel`:
```javascript
import KPICard        from '$lib/components/KPICard.svelte';
import ChartPanel     from '$lib/components/ChartPanel.svelte';
import DataTable      from '$lib/components/DataTable.svelte';
import MapPanel       from '$lib/components/MapPanel.svelte';
import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
```

- [ ] **Step 2: Adicionar branch para `map` no template**

Localizar o bloco de renderização de indicadores (linha ~196, dentro do `{#each indicadores as ind}`):

```svelte
{:else if ind.query_tipo === 'table'}
  <DataTable dados={ind.dados} />

{:else}
  <p class="muted" ...>Tipo "{ind.query_tipo}" não suportado</p>
```

Adicionar o branch `map` **antes** do `{:else}` final:

```svelte
{:else if ind.query_tipo === 'table'}
  <DataTable dados={ind.dados} />

{:else if ind.query_tipo === 'map'}
  <MapPanel pontos={ind.dados ?? []} />

{:else}
  <p class="muted" style="font-size:12px; padding:8px">Tipo "{ind.query_tipo}" não suportado</p>
```

- [ ] **Step 3: Reiniciar frontend**

```bash
docker restart datahub_frontend
```

- [ ] **Step 4: Verificar no painel**

1. Ir em Configurações → Painéis
2. Editar (ou criar) um painel e adicionar a query `teste_mapa` como indicador
3. Abrir o painel — deve mostrar o mapa com 3 círculos representando SP, RJ e BH
4. O mapa deve auto-fit mostrando os 3 pontos
5. Clicar em um círculo deve abrir o popup `<b>São Paulo</b><br>500`
6. O círculo de SP (valor 500) deve ser visivelmente maior que BH (valor 150)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/painel/[slug]/+page.svelte
git commit -m "feat: render MapPanel for map query type in painel"
```

---

## Verificação Final

- [ ] Criar query do tipo `map` — funciona sem erro de validação backend
- [ ] SQL sem `lat` ou `lng` — QueryEditor alerta sobre colunas faltando
- [ ] Mapa no painel — auto-fit nos 3 pontos de teste
- [ ] Popup ao clicar — mostra label e valor
- [ ] Tamanho dos círculos — proporcional ao valor (maior valor = círculo maior)
- [ ] KPI e charts existentes — não foram afetados
