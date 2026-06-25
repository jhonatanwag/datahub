# DataHub — Sistema de Queries Dinâmicas
## Atualização da Stack: Metadata-Driven Dashboard

---

## 1. CONCEITO CENTRAL

```
Tela de Configurações (admin)
      ↓
Cadastra query SQL + tipo + destino + empresa (ou global)
      ↓
Salva em datahub_meta.queries
      ↓
Backend busca query por slug, executa no banco da empresa correta
      ↓
Frontend renderiza KPI / Gráfico / Tabela / Contexto IA dinamicamente
```

Hierarquia de resolução de queries:
```
1. Query específica da empresa   → tem prioridade
2. Query global                  → fallback se não houver específica
3. Erro informativo              → se nenhuma existir
```

---

## 2. NOVAS TABELAS NO DATAHUB_META

```sql
-- Adicionar ao 01_datahub_meta.sql

-- Queries cadastradas (globais ou por empresa)
CREATE TABLE queries (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(100) NOT NULL,        -- identificador único ex: 'kpi_receita'
    nome         VARCHAR(150) NOT NULL,        -- nome legível ex: 'Receita Total (30d)'
    descricao    TEXT,                         -- explicação do que retorna
    sql_texto    TEXT NOT NULL,                -- a query SQL em si
    tipo         VARCHAR(30) NOT NULL,         -- 'kpi' | 'chart_line' | 'chart_bar' |
                                               -- 'chart_bar_horizontal' | 'chart_doughnut' |
                                               -- 'table' | 'rag_context'
    empresa_id   INTEGER REFERENCES empresas(id) NULL,  -- NULL = global
    ativo        BOOLEAN DEFAULT true,
    cache_ttl    INTEGER DEFAULT 300,          -- segundos em cache (0 = sem cache)
    criado_em    TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    UNIQUE (slug, empresa_id)                  -- mesmo slug pode existir global e por empresa
);

-- Parâmetros aceitos por cada query (para filtros dinâmicos)
CREATE TABLE query_parametros (
    id           SERIAL PRIMARY KEY,
    query_id     INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    nome         VARCHAR(50) NOT NULL,         -- ex: 'data_inicio'
    tipo         VARCHAR(20) NOT NULL,         -- 'date' | 'string' | 'integer' | 'boolean'
    obrigatorio  BOOLEAN DEFAULT false,
    valor_padrao TEXT,                         -- ex: 'NOW() - INTERVAL 30 days'
    descricao    TEXT
);

-- Layout do dashboard por empresa (ordem e posição dos widgets)
CREATE TABLE dashboard_layout (
    id           SERIAL PRIMARY KEY,
    empresa_id   INTEGER REFERENCES empresas(id) NULL,  -- NULL = layout global padrão
    query_slug   VARCHAR(100) NOT NULL,
    posicao      INTEGER NOT NULL,             -- ordem de exibição
    largura      VARCHAR(10) DEFAULT 'half',   -- 'full' | 'half' | 'third' | 'quarter'
    titulo       VARCHAR(150),                 -- título do widget (override do nome da query)
    visivel      BOOLEAN DEFAULT true
);

-- Índices
CREATE INDEX idx_queries_slug        ON queries(slug);
CREATE INDEX idx_queries_empresa     ON queries(empresa_id);
CREATE INDEX idx_queries_tipo        ON queries(tipo);
CREATE INDEX idx_layout_empresa      ON dashboard_layout(empresa_id);

-- Trigger para atualizar atualizado_em automaticamente
CREATE OR REPLACE FUNCTION update_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN NEW.atualizado_em = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_queries_updated
BEFORE UPDATE ON queries
FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();
```

---

## 3. QUERIES GLOBAIS DE EXEMPLO (SEEDS)

```sql
-- Seeds iniciais — adapte os nomes de tabelas/colunas para sua realidade

-- KPIs
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl) VALUES
(
  'kpi_receita',
  'Receita Total (30d)',
  'Soma do valor de todos os pedidos nos últimos 30 dias',
  'SELECT COALESCE(SUM(valor), 0) AS valor, ''Receita Total'' AS label, ''R$'' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_pedidos',
  'Total de Pedidos (30d)',
  'Contagem de pedidos nos últimos 30 dias',
  'SELECT COUNT(*) AS valor, ''Pedidos'' AS label, '''' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_ticket_medio',
  'Ticket Médio (30d)',
  'Valor médio por pedido nos últimos 30 dias',
  'SELECT COALESCE(AVG(valor), 0) AS valor, ''Ticket Médio'' AS label, ''R$'' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_clientes',
  'Clientes Ativos (30d)',
  'Clientes distintos com pedido nos últimos 30 dias',
  'SELECT COUNT(DISTINCT cliente_id) AS valor, ''Clientes Ativos'' AS label, '''' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),

-- Gráficos
(
  'chart_receita_mensal',
  'Receita Mensal',
  'Evolução da receita mês a mês nos últimos 12 meses',
  'SELECT TO_CHAR(data, ''Mon'') AS label, COALESCE(SUM(valor), 0) AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''12 months'' GROUP BY 1, EXTRACT(MONTH FROM data) ORDER BY EXTRACT(MONTH FROM data)',
  'chart_line', 600
),
(
  'chart_pedidos_status',
  'Pedidos por Status',
  'Distribuição de pedidos por status',
  'SELECT status AS label, COUNT(*) AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days'' GROUP BY status ORDER BY valor DESC',
  'chart_bar_horizontal', 600
),
(
  'chart_canal_vendas',
  'Canal de Vendas',
  'Distribuição percentual por canal',
  'SELECT canal AS label, COUNT(*) AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days'' GROUP BY canal ORDER BY valor DESC',
  'chart_doughnut', 600
),

-- Tabela
(
  'table_pedidos_recentes',
  'Pedidos Recentes',
  'Últimos pedidos com cliente, valor e status',
  'SELECT id, cliente_nome, produto, valor, status, data FROM pedidos ORDER BY data DESC LIMIT 50',
  'table', 120
),

-- Contexto RAG para o chatbot
(
  'rag_contexto_principal',
  'Contexto Principal para IA',
  'Dados agregados injetados no prompt do chatbot',
  'SELECT ''kpis'' AS secao, json_build_object(''receita'', SUM(valor), ''pedidos'', COUNT(*), ''ticket_medio'', AVG(valor), ''clientes'', COUNT(DISTINCT cliente_id)) AS dados FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'rag_context', 600
);

-- Layout padrão global
INSERT INTO dashboard_layout (empresa_id, query_slug, posicao, largura, titulo) VALUES
(NULL, 'kpi_receita',           1, 'quarter', NULL),
(NULL, 'kpi_pedidos',           2, 'quarter', NULL),
(NULL, 'kpi_ticket_medio',      3, 'quarter', NULL),
(NULL, 'kpi_clientes',          4, 'quarter', NULL),
(NULL, 'chart_receita_mensal',  5, 'half',    NULL),
(NULL, 'chart_pedidos_status',  6, 'half',    NULL),
(NULL, 'chart_canal_vendas',    7, 'half',    NULL),
(NULL, 'table_pedidos_recentes',8, 'full',    NULL);
```

---

## 4. CONTRATO DE RETORNO DAS QUERIES

Para o frontend renderizar corretamente, cada tipo de query
deve retornar colunas com nomes padronizados:

```
kpi
  → valor: numeric          (o número a exibir)
  → label: text             (nome do KPI)
  → prefixo: text           (ex: 'R$', '%', '')
  → delta: numeric (opt)    (variação percentual)
  → delta_dir: text (opt)   ('up' | 'down')

chart_line / chart_bar / chart_bar_horizontal
  → label: text             (eixo X ou categoria)
  → valor: numeric          (eixo Y)
  → serie: text (opt)       (para múltiplas séries)

chart_doughnut
  → label: text             (fatia)
  → valor: numeric          (tamanho da fatia)

table
  → qualquer coluna         (frontend gera cabeçalhos automaticamente)
  → coluna 'status' recebe estilo automático (dot colorido)
  → coluna 'valor' recebe formatação monetária automática

rag_context
  → qualquer estrutura      (convertida para texto e injetada no prompt)
```

---

## 5. BACKEND — NOVOS ARQUIVOS

### backend/services/query_runner.py
```python
"""
Motor de execução de queries dinâmicas.
Busca a query no datahub_meta, executa no banco da empresa correta,
aplica cache Redis e retorna os dados padronizados.
"""
import json
from typing import Optional
from config.databases import query_meta, query_company
from services.cache import cache_get, cache_set


async def resolver_query(
    slug: str,
    company_slug: str,
    empresa_id: int,
    parametros: dict = {}
) -> dict:
    """
    Resolve uma query pelo slug:
    1. Busca query específica da empresa
    2. Fallback para query global
    3. Executa no banco da empresa
    4. Aplica cache
    """

    # 1. Busca query (empresa-específica tem prioridade)
    rows = await query_meta("""
        SELECT q.*
        FROM queries q
        WHERE q.slug = $1
          AND q.ativo = true
          AND (q.empresa_id = $2 OR q.empresa_id IS NULL)
        ORDER BY q.empresa_id NULLS LAST
        LIMIT 1
    """, slug, empresa_id)

    if not rows:
        raise ValueError(f"Query '{slug}' não encontrada ou inativa")

    query = dict(rows[0])

    # 2. Chave de cache
    params_key = json.dumps(parametros, sort_keys=True)
    cache_key = f"query:{slug}:{company_slug}:{params_key}"

    if query["cache_ttl"] > 0:
        cached = await cache_get(cache_key)
        if cached:
            return {"data": cached, "from_cache": True, "query": query["nome"]}

    # 3. Executa no banco da empresa
    sql = query["sql_texto"]

    # Substitui parâmetros seguros (apenas valores tipados, sem interpolação direta)
    # Parâmetros são passados via $1, $2 no SQL e listados em query_parametros
    param_rows = await query_meta(
        "SELECT * FROM query_parametros WHERE query_id = $1 ORDER BY id",
        query["id"]
    )

    # Monta lista de valores na ordem dos parâmetros declarados
    valores = []
    for p in param_rows:
        val = parametros.get(p["nome"], p["valor_padrao"])
        if val is None and p["obrigatorio"]:
            raise ValueError(f"Parâmetro obrigatório ausente: {p['nome']}")
        valores.append(val)

    resultado = await query_company(company_slug, sql, *valores)
    data = [dict(r) for r in resultado]

    # 4. Salva cache
    if query["cache_ttl"] > 0:
        await cache_set(cache_key, data, ttl=query["cache_ttl"])

    return {
        "data": data,
        "from_cache": False,
        "query": query["nome"],
        "tipo": query["tipo"]
    }


async def invalidar_cache_empresa(company_slug: str):
    """Invalida todo o cache de queries de uma empresa."""
    from config.redis import get_redis
    redis = await get_redis()
    keys = await redis.keys(f"query:*:{company_slug}:*")
    if keys:
        await redis.delete(*keys)
```

### backend/services/rag.py (versão dinâmica)
```python
"""
RAG dinâmico: busca queries do tipo 'rag_context' cadastradas
no datahub_meta e as executa para montar o contexto do chatbot.
"""
import json
from config.databases import query_meta
from services.query_runner import resolver_query


async def build_context(company_slug: str, empresa_id: int) -> str:
    """Busca todas as queries rag_context ativas e monta o contexto."""

    # Busca queries de contexto (empresa-específica + global)
    rag_queries = await query_meta("""
        SELECT DISTINCT ON (slug) slug, nome
        FROM queries
        WHERE tipo = 'rag_context'
          AND ativo = true
          AND (empresa_id = $1 OR empresa_id IS NULL)
        ORDER BY slug, empresa_id NULLS LAST
    """, empresa_id)

    if not rag_queries:
        return "Nenhum contexto de dados configurado para esta empresa."

    partes = []
    for q in rag_queries:
        try:
            resultado = await resolver_query(
                slug=q["slug"],
                company_slug=company_slug,
                empresa_id=empresa_id
            )
            partes.append(f"[{q['nome']}]:\n{json.dumps(resultado['data'], default=str, ensure_ascii=False)}")
        except Exception as e:
            partes.append(f"[{q['nome']}]: erro ao buscar dados ({e})")

    return "\n\n".join(partes)
```

### backend/routes/queries.py (CRUD de queries)
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta
from services.query_runner import resolver_query, invalidar_cache_empresa

router = APIRouter(prefix="/api/queries", tags=["Queries"])


# ── Modelos ──

class QueryInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    sql_texto: str
    tipo: str                          # kpi | chart_line | chart_bar | etc
    empresa_id: Optional[int] = None   # None = global
    cache_ttl: int = 300
    ativo: bool = True


class QueryUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    sql_texto: Optional[str] = None
    tipo: Optional[str] = None
    cache_ttl: Optional[int] = None
    ativo: Optional[bool] = None


# ── Listar queries (com filtro por tipo e empresa) ──

@router.get("/")
async def listar_queries(
    tipo: Optional[str] = None,
    empresa_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    filtros = ["1=1"]
    params = []

    if tipo:
        params.append(tipo)
        filtros.append(f"tipo = ${len(params)}")

    if empresa_id is not None:
        params.append(empresa_id)
        filtros.append(f"(empresa_id = ${len(params)} OR empresa_id IS NULL)")

    where = " AND ".join(filtros)
    rows = await query_meta(
        f"SELECT * FROM queries WHERE {where} ORDER BY tipo, nome",
        *params
    )
    return [dict(r) for r in rows]


# ── Buscar query por ID ──

@router.get("/{query_id}")
async def buscar_query(query_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
    if not rows:
        raise HTTPException(404, "Query não encontrada")
    return dict(rows[0])


# ── Criar query ──

@router.post("/")
async def criar_query(body: QueryInput, user=Depends(require_admin)):
    # Valida tipo
    tipos_validos = {
        'kpi', 'chart_line', 'chart_bar',
        'chart_bar_horizontal', 'chart_doughnut',
        'table', 'rag_context'
    }
    if body.tipo not in tipos_validos:
        raise HTTPException(400, f"Tipo inválido. Use: {tipos_validos}")

    rows = await query_meta("""
        INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
    """, body.slug, body.nome, body.descricao, body.sql_texto,
        body.tipo, body.empresa_id, body.cache_ttl, body.ativo)

    return dict(rows[0])


# ── Atualizar query ──

@router.patch("/{query_id}")
async def atualizar_query(
    query_id: int,
    body: QueryUpdate,
    user=Depends(require_admin)
):
    # Busca atual
    atual = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
    if not atual:
        raise HTTPException(404, "Query não encontrada")

    atual = dict(atual[0])
    updates = body.dict(exclude_none=True)

    if not updates:
        return atual

    # Monta SET dinâmico
    campos = []
    valores = []
    for i, (k, v) in enumerate(updates.items(), start=1):
        campos.append(f"{k} = ${i}")
        valores.append(v)

    valores.append(query_id)
    sql = f"UPDATE queries SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
    rows = await query_meta(sql, *valores)

    # Invalida cache da empresa afetada
    if atual.get("empresa_id"):
        emp = await query_meta(
            "SELECT slug FROM empresas WHERE id = $1", atual["empresa_id"]
        )
        if emp:
            await invalidar_cache_empresa(emp[0]["slug"])

    return dict(rows[0])


# ── Deletar query ──

@router.delete("/{query_id}")
async def deletar_query(query_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "DELETE FROM queries WHERE id = $1 RETURNING id, slug", query_id
    )
    if not rows:
        raise HTTPException(404, "Query não encontrada")
    return {"deletado": True, "slug": rows[0]["slug"]}


# ── Testar query (executa e retorna resultado sem salvar) ──

@router.post("/testar")
async def testar_query(body: QueryInput, user=Depends(require_admin)):
    """
    Executa a query no banco da empresa do usuário logado sem salvar.
    Útil para validar o SQL antes de cadastrar.
    """
    try:
        from config.databases import query_company
        resultado = await query_company(
            user["company_slug"], body.sql_texto
        )
        data = [dict(r) for r in resultado[:50]]  # máx 50 linhas no teste
        return {
            "ok": True,
            "linhas": len(data),
            "colunas": list(data[0].keys()) if data else [],
            "amostra": data[:5]
        }
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# ── Executar query por slug (usado pelo dashboard) ──

@router.get("/executar/{slug}")
async def executar_query(
    slug: str,
    user=Depends(get_current_user)
):
    try:
        resultado = await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"]
        )
        return resultado
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erro ao executar query: {e}")


# ── Layout do dashboard ──

@router.get("/layout/dashboard")
async def layout_dashboard(user=Depends(get_current_user)):
    """Retorna o layout do dashboard resolvido para a empresa do usuário."""
    rows = await query_meta("""
        SELECT DISTINCT ON (dl.query_slug)
            dl.query_slug,
            dl.posicao,
            dl.largura,
            COALESCE(dl.titulo, q.nome) AS titulo,
            dl.visivel,
            q.tipo
        FROM dashboard_layout dl
        JOIN queries q ON q.slug = dl.query_slug AND q.ativo = true
        WHERE dl.visivel = true
          AND (dl.empresa_id = $1 OR dl.empresa_id IS NULL)
        ORDER BY dl.query_slug, dl.empresa_id NULLS LAST, dl.posicao
    """, user["empresa_id"])

    # Reordena por posição após o DISTINCT
    layout = sorted([dict(r) for r in rows], key=lambda x: x["posicao"])
    return layout
```

### backend/routes/charts.py (versão dinâmica)
```python
from fastapi import APIRouter, Depends, Query
from typing import Optional
from middleware.auth import get_current_user
from services.query_runner import resolver_query

router = APIRouter(prefix="/api/charts", tags=["Charts"])


@router.get("/{slug}")
async def executar_chart(
    slug: str,
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    user=Depends(get_current_user)
):
    """Executa qualquer query de gráfico ou KPI pelo slug."""
    parametros = {}
    if data_inicio:
        parametros["data_inicio"] = data_inicio
    if data_fim:
        parametros["data_fim"] = data_fim

    try:
        return await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"],
            parametros=parametros
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(404, str(e))
```

---

## 6. FRONTEND — TELA DE CONFIGURAÇÕES

### Estrutura da tela
```
/configuracoes
├── /queries          ← lista todas as queries
│   ├── /nova         ← cadastrar nova query
│   └── /[id]/editar  ← editar query existente
└── /layout           ← arrastar e reorganizar widgets do dashboard
```

### frontend/src/routes/configuracoes/queries/+page.svelte
```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let queries = [];
  let filtroTipo = '';
  let loading = true;

  const tipos = [
    { value: '',                    label: 'Todos' },
    { value: 'kpi',                 label: 'KPI' },
    { value: 'chart_line',          label: 'Gráfico Linha' },
    { value: 'chart_bar',           label: 'Gráfico Barra' },
    { value: 'chart_bar_horizontal',label: 'Barra Horizontal' },
    { value: 'chart_doughnut',      label: 'Rosca' },
    { value: 'table',               label: 'Tabela' },
    { value: 'rag_context',         label: 'Contexto IA' },
  ];

  onMount(async () => {
    queries = await api.listarQueries();
    loading = false;
  });

  $: filtradas = filtroTipo
    ? queries.filter(q => q.tipo === filtroTipo)
    : queries;

  async function toggleAtivo(q) {
    await api.atualizarQuery(q.id, { ativo: !q.ativo });
    q.ativo = !q.ativo;
    queries = queries;
  }

  async function deletar(q) {
    if (!confirm(`Deletar "${q.nome}"?`)) return;
    await api.deletarQuery(q.id);
    queries = queries.filter(x => x.id !== q.id);
  }
</script>

<!-- UI omitida — Claude Code implementa com o design system -->
```

### frontend/src/routes/configuracoes/queries/nova/+page.svelte
```svelte
<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import QueryEditor from '$lib/components/QueryEditor.svelte';

  let form = {
    slug: '', nome: '', descricao: '',
    sql_texto: '', tipo: 'kpi',
    empresa_id: null, cache_ttl: 300, ativo: true
  };

  let testando = false;
  let resultado_teste = null;
  let salvando = false;
  let erro = null;

  async function testar() {
    testando = true;
    resultado_teste = null;
    resultado_teste = await api.testarQuery(form);
    testando = false;
  }

  async function salvar() {
    if (!resultado_teste?.ok) {
      erro = 'Teste a query antes de salvar.';
      return;
    }
    salvando = true;
    await api.criarQuery(form);
    goto('/configuracoes/queries');
  }
</script>

<!-- QueryEditor.svelte renderiza o editor SQL com highlight -->
```

### frontend/src/lib/components/QueryEditor.svelte
```svelte
<!--
  Editor SQL com:
  - Textarea com fonte monospace
  - Botão "Testar" que chama POST /api/queries/testar
  - Painel de resultado: mostra colunas detectadas, amostra de dados
  - Aviso de contrato: verifica se colunas batem com o tipo selecionado
  - Contador de linhas retornadas
-->
<script>
  export let sql = '';
  export let tipo = 'kpi';
  export let onTestar;   // função async passada pelo pai

  let linhas = 0;
  let colunas = [];
  let amostra = [];
  let erro = null;
  let testando = false;

  // Colunas esperadas por tipo
  const contratos = {
    kpi:                  ['valor', 'label'],
    chart_line:           ['label', 'valor'],
    chart_bar:            ['label', 'valor'],
    chart_bar_horizontal: ['label', 'valor'],
    chart_doughnut:       ['label', 'valor'],
    table:                [],              // qualquer coluna
    rag_context:          [],              // qualquer estrutura
  };

  $: colunasEsperadas = contratos[tipo] || [];
  $: colunasFaltando = colunasEsperadas.filter(c => !colunas.includes(c));

  async function testar() {
    testando = true;
    erro = null;
    const res = await onTestar(sql);
    if (res.ok) {
      linhas   = res.linhas;
      colunas  = res.colunas;
      amostra  = res.amostra;
    } else {
      erro = res.erro;
      linhas = 0; colunas = []; amostra = [];
    }
    testando = false;
  }
</script>

<!-- textarea + botão testar + painel resultado + avisos de contrato -->
```

---

## 7. ATUALIZAÇÃO DO FRONTEND — DASHBOARD DINÂMICO

### frontend/src/routes/+page.svelte (versão dinâmica)
```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import KPICard from '$lib/components/KPICard.svelte';
  import ChartPanel from '$lib/components/ChartPanel.svelte';
  import DataTable from '$lib/components/DataTable.svelte';

  let layout = [];       // widgets em ordem
  let dados = {};        // { slug: resultado }
  let loading = true;

  onMount(async () => {
    // 1. Busca layout da empresa
    layout = await api.layoutDashboard();

    // 2. Executa todas as queries em paralelo
    const resultados = await Promise.allSettled(
      layout.map(widget => api.executarQuery(widget.query_slug))
    );

    resultados.forEach((res, i) => {
      const slug = layout[i].query_slug;
      dados[slug] = res.status === 'fulfilled' ? res.value : { erro: res.reason };
    });

    dados = dados;   // trigger reatividade Svelte
    loading = false;
  });
</script>

{#if loading}
  <!-- Skeleton loading -->
{:else}
  <div class="dashboard-grid">
    {#each layout as widget}
      <div class="widget widget--{widget.largura}">
        <h3>{widget.titulo}</h3>

        {#if dados[widget.query_slug]?.erro}
          <p class="erro">Erro ao carregar: {dados[widget.query_slug].erro}</p>

        {:else if widget.tipo === 'kpi'}
          <KPICard dados={dados[widget.query_slug]?.data?.[0]} />

        {:else if widget.tipo.startsWith('chart_')}
          <ChartPanel
            tipo={widget.tipo}
            dados={dados[widget.query_slug]?.data}
          />

        {:else if widget.tipo === 'table'}
          <DataTable dados={dados[widget.query_slug]?.data} />
        {/if}
      </div>
    {/each}
  </div>
{/if}
```

---

## 8. ATUALIZAÇÃO DO API.JS

```javascript
// Adicionar ao frontend/src/lib/api.js

// Queries
listarQueries:  (tipo, empresa_id) => {
  const p = new URLSearchParams();
  if (tipo)       p.append('tipo', tipo);
  if (empresa_id) p.append('empresa_id', empresa_id);
  return request(`/api/queries/?${p}`);
},
buscarQuery:    (id)   => request(`/api/queries/${id}`),
criarQuery:     (data) => request('/api/queries/', { method: 'POST', body: JSON.stringify(data) }),
atualizarQuery: (id, data) => request(`/api/queries/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
deletarQuery:   (id)   => request(`/api/queries/${id}`, { method: 'DELETE' }),
testarQuery:    (data) => request('/api/queries/testar', { method: 'POST', body: JSON.stringify(data) }),
executarQuery:  (slug, params) => {
  const p = new URLSearchParams(params || {});
  return request(`/api/queries/executar/${slug}?${p}`);
},
layoutDashboard: () => request('/api/queries/layout/dashboard'),
```

---

## 9. SEGURANÇA — QUERIES DINÂMICAS

Ponto crítico: o sistema executa SQL digitado pelo usuário.
Aplique estas proteções obrigatórias:

```python
# backend/services/query_runner.py — adicionar validação

PALAVRAS_PROIBIDAS = [
    'drop', 'truncate', 'delete', 'insert', 'update',
    'alter', 'create', 'grant', 'revoke', 'pg_', 'information_schema'
]

def validar_sql(sql: str) -> bool:
    """Permite apenas SELECT. Bloqueia DDL e DML destrutivo."""
    sql_lower = sql.lower().strip()

    if not sql_lower.startswith('select'):
        raise ValueError("Apenas queries SELECT são permitidas")

    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in sql_lower:
            raise ValueError(f"Palavra não permitida: '{palavra}'")

    return True
```

Adicione `validar_sql(body.sql_texto)` em `criar_query` e `testar_query`.

Além disso, cada empresa já tem seu próprio usuário PostgreSQL com
permissões restritas — o pior caso é um SELECT em tabelas que o
usuário já teria acesso.

---

## 10. ATUALIZAÇÃO DO PROMPT.MD

Adicione esta fase ao `PROMPT.md` após a Fase 6:

```markdown
## FASE 6.5 — SISTEMA DE QUERIES DINÂMICAS

### 6.5.1 SQL adicional — `backend/sql/02_queries_dinamicas.sql`
Copie as tabelas `queries`, `query_parametros` e `dashboard_layout`
do `arquitetura-queries-dinamicas.md`, seção 2.
Inclua os seeds da seção 3.

[PERGUNTAR] Quais são os nomes reais das tabelas e colunas
nos bancos das empresas? Com essa informação atualizo os
seeds para refletir a estrutura real de dados.

### 6.5.2 `backend/services/query_runner.py`
Copie do `arquitetura-queries-dinamicas.md`, seção 5.
Inclua a função `validar_sql` da seção 9.

### 6.5.3 `backend/services/rag.py`
Substitua pelo código da seção 5 (versão dinâmica).

### 6.5.4 `backend/routes/queries.py`
Copie da seção 5. Certifique-se de que `validar_sql`
é chamado em `criar_query` e `testar_query`.

### 6.5.5 `backend/routes/charts.py`
Substitua pelo código da seção 5 (versão dinâmica).

### 6.5.6 Frontend — tela de configurações
Crie as rotas e componentes da seção 6.
O `QueryEditor.svelte` deve mostrar aviso visual
quando as colunas retornadas não batem com o contrato do tipo.

### 6.5.7 Dashboard dinâmico
Substitua `frontend/src/routes/+page.svelte` pelo
código da seção 7.

### 6.5.8 api.js
Adicione os métodos da seção 8.

Checklist desta fase:
- [ ] POST /api/queries/testar retorna colunas da query
- [ ] GET /api/queries/layout/dashboard retorna layout ordenado
- [ ] GET /api/queries/executar/kpi_receita retorna { data, tipo }
- [ ] Dashboard carrega widgets dinamicamente pelo layout
- [ ] SQL com DROP é rejeitado com erro 400
- [ ] Query empresa-específica tem prioridade sobre global
```
