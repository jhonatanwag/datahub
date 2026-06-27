# PROMPT-PAINEIS.md — Sistema de Painéis Dinâmicos
## Leia este arquivo inteiro antes de escrever qualquer código.

---

## VISÃO GERAL

O sistema de painéis é o coração do DataHub.
Permite que o admin construa dashboards personalizados
sem escrever código — apenas configurando no painel administrativo.

### Fluxo completo:

```
1. Admin cadastra Variáveis (filtros reutilizáveis)
        ↓
2. Admin cadastra Queries (usando :variaveis no SQL)
        ↓
3. Admin cadastra Painel (grid + indicadores + filtros)
        ↓
4. Admin vincula Painel aos Usuários
        ↓
5. Usuário loga → Menu carrega os painéis dele automaticamente
        ↓
6. Usuário aplica filtros → todos os indicadores reagem
```

---

## REGRAS

1. Não apague código existente — apenas adicione.
2. Siga a ordem exata das fases.
3. Teste cada fase antes de avançar.
4. Pause nas tags [PERGUNTAR].

---

## FASE 1 — BANCO DE DADOS: NOVAS TABELAS

### 1.1 Criar arquivo `backend/sql/03_paineis.sql`

```sql
-- ── Variáveis (filtros reutilizáveis) ─────────────────────────

CREATE TABLE variaveis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,  -- ex: 'periodo', 'vendedor'
    nome          VARCHAR(150) NOT NULL,          -- ex: 'Período', 'Vendedor'
    descricao     TEXT,
    tipo          VARCHAR(30) NOT NULL,
    -- tipos: 'date' | 'date_range' | 'select' | 'multiselect' | 'text' | 'number'
    query_fonte   TEXT,           -- SQL que popula o dropdown (para select/multiselect)
    -- ex: SELECT id AS valor, nome AS label FROM vendedores ORDER BY nome
    param_names   TEXT[],         -- parâmetros gerados ex: '{data_inicio,data_fim}'
    ativo         BOOLEAN DEFAULT true,
    criado_em     TIMESTAMP DEFAULT NOW()
);

-- ── Painéis ───────────────────────────────────────────────────

CREATE TABLE paineis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    icone         VARCHAR(50) DEFAULT 'chart-bar',  -- ícone do menu
    colunas       INTEGER NOT NULL DEFAULT 3,        -- colunas do grid
    linhas_fixas  BOOLEAN DEFAULT false,             -- false = contínuo
    total_linhas  INTEGER,                           -- só se linhas_fixas = true
    empresa_id    INTEGER REFERENCES empresas(id) NULL,  -- NULL = global
    ativo         BOOLEAN DEFAULT true,
    ordem_menu    INTEGER DEFAULT 0,                 -- ordem no menu lateral
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- ── Indicadores dentro do painel ─────────────────────────────

CREATE TABLE painel_indicadores (
    id              SERIAL PRIMARY KEY,
    painel_id       INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    query_slug      VARCHAR(100) NOT NULL,
    titulo          VARCHAR(150),        -- override do título da query
    linha           INTEGER NOT NULL,    -- posição linha (começa em 1)
    coluna          INTEGER NOT NULL,    -- posição coluna (começa em 1)
    col_span        INTEGER DEFAULT 1,   -- quantas colunas ocupa
    row_span        INTEGER DEFAULT 1,   -- quantas linhas ocupa
    posicao         INTEGER DEFAULT 0,   -- ordem de renderização
    UNIQUE (painel_id, linha, coluna)
);

-- ── Variáveis ativas em cada painel (filtros) ─────────────────

CREATE TABLE painel_variaveis (
    id            SERIAL PRIMARY KEY,
    painel_id     INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    variavel_id   INTEGER REFERENCES variaveis(id),
    obrigatorio   BOOLEAN DEFAULT false,
    valor_padrao  TEXT,             -- valor inicial do filtro
    posicao       INTEGER DEFAULT 0,-- ordem dos filtros no painel
    UNIQUE (painel_id, variavel_id)
);

-- ── Acesso de usuários aos painéis ───────────────────────────

CREATE TABLE painel_usuarios (
    painel_id     INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY   (painel_id, usuario_id)
);

-- ── Índices ──────────────────────────────────────────────────

CREATE INDEX idx_paineis_empresa    ON paineis(empresa_id);
CREATE INDEX idx_paineis_ativo      ON paineis(ativo);
CREATE INDEX idx_painel_ind_painel  ON painel_indicadores(painel_id);
CREATE INDEX idx_painel_var_painel  ON painel_variaveis(painel_id);
CREATE INDEX idx_painel_usr_usuario ON painel_usuarios(usuario_id);

-- ── Trigger atualizado_em ─────────────────────────────────────

CREATE TRIGGER trg_paineis_updated
BEFORE UPDATE ON paineis
FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();

-- ── Seeds: variáveis padrão ───────────────────────────────────

INSERT INTO variaveis (slug, nome, descricao, tipo, param_names) VALUES
(
  'periodo',
  'Período',
  'Filtro de intervalo de datas',
  'date_range',
  ARRAY['data_inicio', 'data_fim']
),
(
  'data_unica',
  'Data',
  'Filtro de data única',
  'date',
  ARRAY['data']
),
(
  'texto_livre',
  'Busca',
  'Campo de texto livre para busca',
  'text',
  ARRAY['busca']
);

-- ── Seeds: painel de exemplo ──────────────────────────────────

INSERT INTO paineis (slug, nome, descricao, colunas, linhas_fixas, empresa_id, ordem_menu)
VALUES ('visao_geral', 'Visão Geral', 'Dashboard principal com KPIs', 4, false, NULL, 1);

-- Indicadores do painel de exemplo
INSERT INTO painel_indicadores (painel_id, query_slug, linha, coluna, col_span, titulo)
VALUES
  (1, 'kpi_receita',          1, 1, 1, NULL),
  (1, 'kpi_pedidos',          1, 2, 1, NULL),
  (1, 'kpi_ticket_medio',     1, 3, 1, NULL),
  (1, 'kpi_clientes',         1, 4, 1, NULL),
  (1, 'chart_receita_mensal', 2, 1, 2, NULL),
  (1, 'chart_pedidos_status', 2, 3, 2, NULL),
  (1, 'table_pedidos_recentes',3, 1, 4, NULL);

-- Filtro de período no painel de exemplo
INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
VALUES (1, 1, false, 1);

-- Dar acesso ao admin (usuário 1) ao painel de exemplo
INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES (1, 1);
```

### 1.2 Executar no banco:

```bash
docker exec -i datahub_postgres psql -U postgres -d datahub_meta < backend/sql/03_paineis.sql
```

---

## FASE 2 — BACKEND: VARIÁVEIS

### `backend/routes/variaveis.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta

router = APIRouter(prefix="/api/variaveis", tags=["Variáveis"])


class VariavelInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    tipo: str           # date | date_range | select | multiselect | text | number
    query_fonte: Optional[str] = None   # SQL para select/multiselect
    param_names: List[str] = []
    ativo: bool = True


# Tipos válidos
TIPOS_VALIDOS = {'date', 'date_range', 'select', 'multiselect', 'text', 'number'}


@router.get("/")
async def listar_variaveis(user=Depends(get_current_user)):
    rows = await query_meta(
        "SELECT * FROM variaveis WHERE ativo = true ORDER BY nome"
    )
    return [dict(r) for r in rows]


@router.get("/{variavel_id}")
async def buscar_variavel(variavel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not rows:
        raise HTTPException(404, "Variável não encontrada")
    return dict(rows[0])


@router.post("/")
async def criar_variavel(body: VariavelInput, user=Depends(require_admin)):
    if body.tipo not in TIPOS_VALIDOS:
        raise HTTPException(400, f"Tipo inválido. Use: {TIPOS_VALIDOS}")

    if body.tipo in ('select', 'multiselect') and not body.query_fonte:
        raise HTTPException(400, "query_fonte é obrigatório para select/multiselect")

    rows = await query_meta("""
        INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, param_names, ativo)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
    """, body.slug, body.nome, body.descricao, body.tipo,
        body.query_fonte, body.param_names, body.ativo)

    return dict(rows[0])


@router.patch("/{variavel_id}")
async def atualizar_variavel(
    variavel_id: int,
    body: dict,
    user=Depends(require_admin)
):
    atual = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not atual:
        raise HTTPException(404, "Variável não encontrada")

    campos = []
    valores = []
    for i, (k, v) in enumerate(body.items(), start=1):
        campos.append(f"{k} = ${i}")
        valores.append(v)

    valores.append(variavel_id)
    sql = f"UPDATE variaveis SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
    rows = await query_meta(sql, *valores)
    return dict(rows[0])


@router.delete("/{variavel_id}")
async def deletar_variavel(variavel_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "UPDATE variaveis SET ativo = false WHERE id = $1 RETURNING id, slug",
        variavel_id
    )
    if not rows:
        raise HTTPException(404, "Variável não encontrada")
    return {"desativado": True, "slug": rows[0]["slug"]}


@router.post("/executar-fonte/{variavel_id}")
async def executar_fonte_variavel(
    variavel_id: int,
    user=Depends(get_current_user)
):
    """Executa a query_fonte da variável no banco da empresa ativa."""
    variavel = await query_meta("SELECT * FROM variaveis WHERE id = $1", variavel_id)
    if not variavel:
        raise HTTPException(404, "Variável não encontrada")

    v = dict(variavel[0])
    if not v.get("query_fonte"):
        raise HTTPException(400, "Esta variável não tem query_fonte")

    from config.databases import query_company
    try:
        rows = await query_company(user["company_slug"], v["query_fonte"])
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(500, f"Erro ao executar query_fonte: {e}")
```

---

## FASE 3 — BACKEND: PAINÉIS

### `backend/routes/paineis.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta

router = APIRouter(prefix="/api/paineis", tags=["Painéis"])


class PainelInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    icone: str = 'chart-bar'
    colunas: int = 3
    linhas_fixas: bool = False
    total_linhas: Optional[int] = None
    empresa_id: Optional[int] = None
    ativo: bool = True
    ordem_menu: int = 0


class IndicadorInput(BaseModel):
    query_slug: str
    titulo: Optional[str] = None
    linha: int
    coluna: int
    col_span: int = 1
    row_span: int = 1
    posicao: int = 0


class VariavelPainelInput(BaseModel):
    variavel_id: int
    obrigatorio: bool = False
    valor_padrao: Optional[str] = None
    posicao: int = 0


# ── CRUD Painéis ─────────────────────────────────────────────

@router.get("/")
async def listar_paineis(user=Depends(get_current_user)):
    """Lista painéis. Admin vê todos, viewer só os seus."""
    if user["role"] == "admin":
        rows = await query_meta(
            "SELECT * FROM paineis ORDER BY ordem_menu, nome"
        )
    else:
        rows = await query_meta("""
            SELECT p.* FROM paineis p
            JOIN painel_usuarios pu ON pu.painel_id = p.id
            WHERE pu.usuario_id = $1 AND p.ativo = true
            ORDER BY p.ordem_menu, p.nome
        """, user["id"])
    return [dict(r) for r in rows]


@router.get("/meu-menu")
async def meu_menu(user=Depends(get_current_user)):
    """
    Retorna os painéis do usuário para montar o menu lateral.
    Resolve hierarquia: painel da empresa tem prioridade sobre global.
    """
    rows = await query_meta("""
        SELECT DISTINCT ON (p.slug)
            p.id, p.slug, p.nome, p.icone, p.ordem_menu, p.empresa_id
        FROM paineis p
        JOIN painel_usuarios pu ON pu.painel_id = p.id
        WHERE pu.usuario_id = $1
          AND p.ativo = true
          AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
        ORDER BY p.slug, p.empresa_id NULLS LAST, p.ordem_menu
    """, user["id"], user["empresa_id"])

    return sorted([dict(r) for r in rows], key=lambda x: x["ordem_menu"])


@router.get("/{painel_id}")
async def buscar_painel(painel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    return dict(rows[0])


@router.get("/slug/{slug}")
async def buscar_painel_por_slug(slug: str, user=Depends(get_current_user)):
    """Busca painel por slug — usado pelo frontend para renderizar."""
    rows = await query_meta("""
        SELECT DISTINCT ON (p.slug) p.*
        FROM paineis p
        JOIN painel_usuarios pu ON pu.painel_id = p.id
        WHERE p.slug = $1
          AND pu.usuario_id = $2
          AND p.ativo = true
          AND (p.empresa_id = $3 OR p.empresa_id IS NULL)
        ORDER BY p.slug, p.empresa_id NULLS LAST
    """, slug, user["id"], user["empresa_id"])

    if not rows:
        raise HTTPException(404, "Painel não encontrado ou sem acesso")
    return dict(rows[0])


@router.post("/")
async def criar_painel(body: PainelInput, user=Depends(require_admin)):
    rows = await query_meta("""
        INSERT INTO paineis
            (slug, nome, descricao, icone, colunas, linhas_fixas,
             total_linhas, empresa_id, ativo, ordem_menu)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING *
    """, body.slug, body.nome, body.descricao, body.icone,
        body.colunas, body.linhas_fixas, body.total_linhas,
        body.empresa_id, body.ativo, body.ordem_menu)
    return dict(rows[0])


@router.patch("/{painel_id}")
async def atualizar_painel(
    painel_id: int, body: dict, user=Depends(require_admin)
):
    atual = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not atual:
        raise HTTPException(404, "Painel não encontrado")

    campos = []
    valores = []
    for i, (k, v) in enumerate(body.items(), start=1):
        campos.append(f"{k} = ${i}")
        valores.append(v)

    valores.append(painel_id)
    sql = f"UPDATE paineis SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
    rows = await query_meta(sql, *valores)
    return dict(rows[0])


@router.delete("/{painel_id}")
async def desativar_painel(painel_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "UPDATE paineis SET ativo = false WHERE id = $1 RETURNING id, slug",
        painel_id
    )
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
    return {"desativado": True, "slug": rows[0]["slug"]}


# ── Indicadores do painel ─────────────────────────────────────

@router.get("/{painel_id}/indicadores")
async def listar_indicadores(painel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("""
        SELECT pi.*, q.nome AS query_nome, q.tipo AS query_tipo
        FROM painel_indicadores pi
        JOIN queries q ON q.slug = pi.query_slug
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
    return [dict(r) for r in rows]


@router.post("/{painel_id}/indicadores")
async def adicionar_indicador(
    painel_id: int, body: IndicadorInput, user=Depends(require_admin)
):
    # Valida que a query existe
    q = await query_meta("SELECT id FROM queries WHERE slug = $1", body.query_slug)
    if not q:
        raise HTTPException(404, f"Query '{body.query_slug}' não encontrada")

    rows = await query_meta("""
        INSERT INTO painel_indicadores
            (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING *
    """, painel_id, body.query_slug, body.titulo,
        body.linha, body.coluna, body.col_span, body.row_span, body.posicao)
    return dict(rows[0])


@router.put("/{painel_id}/indicadores")
async def salvar_indicadores(
    painel_id: int,
    indicadores: List[IndicadorInput],
    user=Depends(require_admin)
):
    """Salva layout completo do painel (substitui todos os indicadores)."""
    await query_meta(
        "DELETE FROM painel_indicadores WHERE painel_id = $1", painel_id
    )
    resultado = []
    for ind in indicadores:
        rows = await query_meta("""
            INSERT INTO painel_indicadores
                (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING *
        """, painel_id, ind.query_slug, ind.titulo,
            ind.linha, ind.coluna, ind.col_span, ind.row_span, ind.posicao)
        resultado.append(dict(rows[0]))
    return resultado


@router.delete("/{painel_id}/indicadores/{indicador_id}")
async def remover_indicador(
    painel_id: int, indicador_id: int, user=Depends(require_admin)
):
    await query_meta(
        "DELETE FROM painel_indicadores WHERE id = $1 AND painel_id = $2",
        indicador_id, painel_id
    )
    return {"removido": True}


# ── Variáveis (filtros) do painel ─────────────────────────────

@router.get("/{painel_id}/variaveis")
async def listar_variaveis_painel(painel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("""
        SELECT pv.*, v.slug, v.nome, v.tipo, v.query_fonte, v.param_names
        FROM painel_variaveis pv
        JOIN variaveis v ON v.id = pv.variavel_id
        WHERE pv.painel_id = $1
        ORDER BY pv.posicao
    """, painel_id)
    return [dict(r) for r in rows]


@router.put("/{painel_id}/variaveis")
async def salvar_variaveis_painel(
    painel_id: int,
    variaveis: List[VariavelPainelInput],
    user=Depends(require_admin)
):
    """Salva filtros do painel (substitui todos)."""
    await query_meta(
        "DELETE FROM painel_variaveis WHERE painel_id = $1", painel_id
    )
    resultado = []
    for v in variaveis:
        rows = await query_meta("""
            INSERT INTO painel_variaveis
                (painel_id, variavel_id, obrigatorio, valor_padrao, posicao)
            VALUES ($1,$2,$3,$4,$5)
            RETURNING *
        """, painel_id, v.variavel_id, v.obrigatorio, v.valor_padrao, v.posicao)
        resultado.append(dict(rows[0]))
    return resultado


# ── Usuários com acesso ao painel ─────────────────────────────

@router.get("/{painel_id}/usuarios")
async def listar_usuarios_painel(painel_id: int, user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT u.id, u.nome, u.email, u.role
        FROM usuarios u
        JOIN painel_usuarios pu ON pu.usuario_id = u.id
        WHERE pu.painel_id = $1
    """, painel_id)
    return [dict(r) for r in rows]


@router.put("/{painel_id}/usuarios")
async def salvar_usuarios_painel(
    painel_id: int,
    usuario_ids: List[int],
    user=Depends(require_admin)
):
    """Define quais usuários têm acesso ao painel."""
    await query_meta(
        "DELETE FROM painel_usuarios WHERE painel_id = $1", painel_id
    )
    for uid in usuario_ids:
        await query_meta(
            "INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES ($1, $2)",
            painel_id, uid
        )
    return {"ok": True, "usuarios": usuario_ids}
```

---

## FASE 4 — BACKEND: EXECUÇÃO DO PAINEL COMPLETO

### `backend/routes/paineis.py` — adicionar rota de renderização

```python
@router.get("/{painel_id}/renderizar")
async def renderizar_painel(
    painel_id: int,
    user=Depends(get_current_user),
    # Filtros dinâmicos passados como query params
    # ex: ?data_inicio=2026-01-01&data_fim=2026-06-30
    **filtros
):
    """
    Executa todas as queries do painel com os filtros aplicados.
    Retorna estrutura pronta para o frontend renderizar o grid.
    """
    from services.query_runner import resolver_query
    from services.cache import cache_get, cache_set
    import json
    from fastapi import Request

    # Busca painel e indicadores
    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        raise HTTPException(404, "Painel não encontrado")

    indicadores = await query_meta("""
        SELECT * FROM painel_indicadores
        WHERE painel_id = $1
        ORDER BY linha, coluna
    """, painel_id)

    # Executa cada query com os filtros
    resultado = []
    for ind in indicadores:
        ind_dict = dict(ind)
        try:
            dados = await resolver_query(
                slug=ind_dict["query_slug"],
                company_slug=user["company_slug"],
                empresa_id=user["empresa_id"],
                parametros=filtros  # filtros das variáveis
            )
            ind_dict["dados"] = dados
            ind_dict["erro"] = None
        except Exception as e:
            ind_dict["dados"] = None
            ind_dict["erro"] = str(e)

        resultado.append(ind_dict)

    return {
        "painel": dict(painel_rows[0]),
        "indicadores": resultado
    }
```

---

## FASE 5 — FRONTEND: MENU DINÂMICO

### `frontend/src/routes/+layout.svelte` — atualizar sidebar

O menu lateral deve carregar dinamicamente os painéis do usuário:

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import { empresaAtiva, usuario } from '$lib/stores/auth.js';

  let menus = [];
  let carregando = true;

  onMount(async () => {
    try {
      menus = await api.meuMenu();
    } catch(e) {
      console.error('Erro ao carregar menu:', e);
    } finally {
      carregando = false;
    }
  });
</script>

<!-- Sidebar -->
<nav>
  <!-- Itens fixos -->
  <a href="/">Dashboard</a>
  <a href="/ai">Assistente IA</a>

  <!-- Divisor -->
  <span class="menu-label">Meus Painéis</span>

  <!-- Painéis dinâmicos -->
  {#if carregando}
    <span class="loading">Carregando...</span>
  {:else}
    {#each menus as painel}
      <a href="/painel/{painel.slug}">
        <span class="icon">{painel.icone}</span>
        {painel.nome}
      </a>
    {/each}
  {/if}

  <!-- Admin only -->
  {#if $usuario?.role === 'admin'}
    <span class="menu-label">Administração</span>
    <a href="/configuracoes/paineis">Painéis</a>
    <a href="/configuracoes/variaveis">Variáveis</a>
    <a href="/configuracoes/queries">Queries</a>
    <a href="/configuracoes/empresas">Empresas</a>
    <a href="/configuracoes/usuarios">Usuários</a>
  {/if}
</nav>
```

---

## FASE 6 — FRONTEND: PÁGINA DO PAINEL

### `frontend/src/routes/painel/[slug]/+page.svelte`

Esta é a página mais importante — renderiza qualquer painel dinamicamente.

**Comportamento:**
1. Lê o `slug` da URL
2. Busca o painel via `GET /api/paineis/slug/{slug}`
3. Busca as variáveis (filtros) do painel
4. Renderiza a barra de filtros no topo
5. Renderiza o grid CSS com os indicadores
6. Quando filtro muda → rebusca os dados

```svelte
<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import KPICard from '$lib/components/KPICard.svelte';
  import ChartPanel from '$lib/components/ChartPanel.svelte';
  import DataTable from '$lib/components/DataTable.svelte';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';

  let slug = $page.params.slug;
  let painel = null;
  let indicadores = [];
  let variaveis = [];
  let filtrosAtivos = {};   // { data_inicio: '...', data_fim: '...' }
  let carregando = true;

  onMount(async () => {
    painel = await api.buscarPainelPorSlug(slug);
    variaveis = await api.variaveisPainel(painel.id);

    // Inicializa filtros com valores padrão
    variaveis.forEach(v => {
      if (v.valor_padrao) {
        v.param_names.forEach(p => filtrosAtivos[p] = v.valor_padrao);
      }
    });

    await carregarDados();
  });

  async function carregarDados() {
    carregando = true;
    const resultado = await api.renderizarPainel(painel.id, filtrosAtivos);
    indicadores = resultado.indicadores;
    carregando = false;
  }

  function onFiltroMudou(event) {
    filtrosAtivos = { ...filtrosAtivos, ...event.detail };
    carregarDados();
  }
</script>

<!-- Título do painel -->
<h1>{painel?.nome}</h1>

<!-- Barra de filtros (só aparece se tiver variáveis) -->
{#if variaveis.length > 0}
  <div class="filtros-bar">
    {#each variaveis as variavel}
      <FiltroVariavel
        {variavel}
        valor={filtrosAtivos}
        on:mudou={onFiltroMudou}
      />
    {/each}
    <button onclick={carregarDados}>Aplicar</button>
  </div>
{/if}

<!-- Grid dinâmico -->
{#if !carregando}
  <div
    class="painel-grid"
    style="grid-template-columns: repeat({painel.colunas}, 1fr)"
  >
    {#each indicadores as ind}
      <div
        class="grid-item"
        style="
          grid-column: {ind.coluna} / span {ind.col_span};
          grid-row: {ind.linha} / span {ind.row_span};
        "
      >
        <div class="card-titulo">{ind.titulo || ind.query_slug}</div>

        {#if ind.erro}
          <p class="erro">{ind.erro}</p>

        {:else if ind.query_tipo === 'kpi'}
          <KPICard dados={ind.dados?.[0]} />

        {:else if ind.query_tipo?.startsWith('chart_')}
          <ChartPanel tipo={ind.query_tipo} dados={ind.dados} />

        {:else if ind.query_tipo === 'table'}
          <DataTable dados={ind.dados} />
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <div class="loading-grid">Carregando painel...</div>
{/if}

<style>
  .painel-grid {
    display: grid;
    gap: 16px;
    padding: 24px;
  }
</style>
```

---

## FASE 7 — FRONTEND: COMPONENTE DE FILTRO

### `frontend/src/lib/components/FiltroVariavel.svelte`

```svelte
<!--
  Renderiza o filtro correto baseado no tipo da variável:
  - date_range → dois campos de data (início e fim)
  - date       → um campo de data
  - select     → dropdown com opções da query_fonte
  - multiselect→ select múltiplo
  - text       → campo de texto
  - number     → campo numérico
-->
<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '$lib/api.js';

  export let variavel;
  export let valor = {};

  const dispatch = createEventDispatcher();
  let opcoes = [];

  onMount(async () => {
    if (variavel.tipo === 'select' || variavel.tipo === 'multiselect') {
      opcoes = await api.executarFonteVariavel(variavel.variavel_id);
    }
  });

  function emitir(params) {
    dispatch('mudou', params);
  }
</script>

<div class="filtro-item">
  <label>{variavel.nome}</label>

  {#if variavel.tipo === 'date_range'}
    <input type="date"
      value={valor.data_inicio || ''}
      onchange={e => emitir({ data_inicio: e.target.value })}
    />
    <span>até</span>
    <input type="date"
      value={valor.data_fim || ''}
      onchange={e => emitir({ data_fim: e.target.value })}
    />

  {:else if variavel.tipo === 'date'}
    <input type="date"
      value={valor.data || ''}
      onchange={e => emitir({ data: e.target.value })}
    />

  {:else if variavel.tipo === 'select'}
    <select onchange={e => emitir({ [variavel.param_names[0]]: e.target.value })}>
      <option value="">Todos</option>
      {#each opcoes as opt}
        <option value={opt.valor}>{opt.label}</option>
      {/each}
    </select>

  {:else if variavel.tipo === 'text'}
    <input type="text"
      placeholder="Buscar..."
      oninput={e => emitir({ [variavel.param_names[0]]: e.target.value })}
    />

  {:else if variavel.tipo === 'number'}
    <input type="number"
      oninput={e => emitir({ [variavel.param_names[0]]: e.target.value })}
    />
  {/if}
</div>
```

---

## FASE 8 — FRONTEND: TELAS DE CONFIGURAÇÃO DE PAINÉIS (admin)

### `/configuracoes/paineis/+page.svelte`
- Cards com nome, icone, colunas, empresa (global ou específica)
- Status ativo/inativo
- Botão "Novo Painel"
- Botão editar e desativar por card

### `/configuracoes/paineis/novo/+page.svelte`

**Formulário em 3 abas:**

```
Aba 1 — Configurações Gerais
  [ Nome do painel          ]
  [ Slug (auto)             ]
  [ Ícone                   ]  seletor de ícone
  [ Descrição               ]
  [ Empresa                 ]  Global / Empresa específica
  [ Colunas do grid: 1-12  ]
  [ Linhas ] ○ Contínuas  ● Fixas: [ número ]
  [ Ordem no menu           ]

Aba 2 — Indicadores
  Preview do grid à direita
  Lista de queries disponíveis à esquerda

  Para cada indicador:
    [ Query          ] dropdown das queries cadastradas
    [ Título         ] override opcional
    [ Linha / Coluna ]
    [ Col span / Row span ]

  Botão "+ Adicionar Indicador"
  O preview atualiza em tempo real

Aba 3 — Filtros e Acesso
  Variáveis disponíveis (todas as ativas):
    [ ] Período       → obrigatório? [ ] valor padrão [    ]
    [ ] Vendedor      → obrigatório? [ ] valor padrão [    ]
    [ ] Busca         → obrigatório? [ ] valor padrão [    ]

  Usuários com acesso:
    [x] Admin
    [ ] João Silva
    [ ] Maria Costa
    (checkboxes de todos os usuários ativos)

[ Cancelar ]  [ Salvar Painel ]
```

### `/configuracoes/variaveis/+page.svelte`
- Tabela: nome, slug, tipo, tem query_fonte?
- Botão "Nova Variável"
- Editar e desativar por linha

### `/configuracoes/variaveis/nova/+page.svelte`

```
[ Nome              ]
[ Slug (auto)       ]
[ Tipo              ]  date | date_range | select | multiselect | text | number

Se tipo = select ou multiselect:
  [ Query fonte (SQL) ]  editor SQL
  [ Botão Testar      ]  mostra amostra das opções

[ Parâmetros gerados ]  readonly, calculado pelo tipo
  → date_range: data_inicio, data_fim
  → select: nome_do_slug

[ Salvar ]
```

---

## FASE 9 — API.JS: NOVOS MÉTODOS

```javascript
// Variáveis
listarVariaveis:        ()    => request('/api/variaveis/'),
criarVariavel:          (d)   => request('/api/variaveis/', { method: 'POST', body: JSON.stringify(d) }),
atualizarVariavel:      (id, d) => request(`/api/variaveis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
desativarVariavel:      (id)  => request(`/api/variaveis/${id}`, { method: 'DELETE' }),
executarFonteVariavel:  (id)  => request(`/api/variaveis/executar-fonte/${id}`),

// Painéis
listarPaineis:          ()    => request('/api/paineis/'),
meuMenu:                ()    => request('/api/paineis/meu-menu'),
buscarPainelPorSlug:    (slug)=> request(`/api/paineis/slug/${slug}`),
criarPainel:            (d)   => request('/api/paineis/', { method: 'POST', body: JSON.stringify(d) }),
atualizarPainel:        (id, d) => request(`/api/paineis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
desativarPainel:        (id)  => request(`/api/paineis/${id}`, { method: 'DELETE' }),

// Indicadores do painel
indicadoresPainel:      (id)  => request(`/api/paineis/${id}/indicadores`),
salvarIndicadores:      (id, d) => request(`/api/paineis/${id}/indicadores`, { method: 'PUT', body: JSON.stringify(d) }),

// Variáveis do painel
variaveisPainel:        (id)  => request(`/api/paineis/${id}/variaveis`),
salvarVariaveisPainel:  (id, d) => request(`/api/paineis/${id}/variaveis`, { method: 'PUT', body: JSON.stringify(d) }),

// Usuários do painel
usuariosPainel:         (id)  => request(`/api/paineis/${id}/usuarios`),
salvarUsuariosPainel:   (id, d) => request(`/api/paineis/${id}/usuarios`, { method: 'PUT', body: JSON.stringify(d) }),

// Renderização
renderizarPainel:       (id, filtros) => {
    const p = new URLSearchParams(filtros || {});
    return request(`/api/paineis/${id}/renderizar?${p}`);
},
```

---

## FASE 10 — REGISTRAR ROTAS NO MAIN.PY

```python
# Adicionar ao backend/main.py
from routes import variaveis, paineis

app.include_router(variaveis.router)
app.include_router(paineis.router)
```

---

## CHECKLIST FINAL

- [ ] SQL executado sem erros no datahub_meta
- [ ] GET /api/paineis/meu-menu retorna painéis do usuário
- [ ] GET /api/paineis/slug/visao_geral retorna o painel de exemplo
- [ ] GET /api/paineis/{id}/renderizar retorna indicadores com dados
- [ ] Menu lateral carrega painéis dinamicamente após login
- [ ] Página /painel/visao_geral renderiza o grid corretamente
- [ ] Filtro de período recarrega os indicadores ao aplicar
- [ ] Admin vê menu de configurações de painéis e variáveis
- [ ] Formulário de novo painel salva com indicadores e filtros
- [ ] Formulário de nova variável com tipo select testa query_fonte
- [ ] Usuários sem acesso não veem o painel no menu
- [ ] Painel empresa-específica só aparece para usuários daquela empresa
