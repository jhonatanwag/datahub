# Painéis Dinâmicos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o sistema completo de painéis dinâmicos — banco, backend (CRUD + renderização) e frontend (menu, página do painel, configurações admin).

**Architecture:** Novas tabelas no `datahub_meta` (variaveis, paineis, painel_indicadores, painel_variaveis, painel_usuarios). Backend FastAPI com dois routers novos (`/api/variaveis`, `/api/paineis`). Frontend SvelteKit com menu dinâmico carregado via API, página de painel com grid CSS dinâmico e páginas admin de CRUD.

**Tech Stack:** PostgreSQL (asyncpg), FastAPI, SvelteKit 2, Svelte 5

## Global Constraints

- Não apagar código existente — apenas adicionar
- Backend usa `query_meta` e `query_company` de `config.databases`
- Auth via `get_current_user` / `require_admin` de `middleware.auth`
- `resolver_query(slug, company_slug, empresa_id, parametros)` retorna `{"data": [...], "tipo": "...", "query": "...", "from_cache": bool}`
- Frontend usa `$lib/api.js` para todas as chamadas; autenticação via `localStorage.getItem('token')`
- Svelte 5: usar `onclick=` (não `on:click=`), `oninput=`, `onchange=`; mas manter `on:click` nos componentes existentes que já usam a sintaxe antiga

---

## Task 1: SQL — Criar schema de painéis

**Files:**
- Create: `backend/sql/03_paineis.sql`

**Interfaces:**
- Produces: tabelas `variaveis`, `paineis`, `painel_indicadores`, `painel_variaveis`, `painel_usuarios`

- [ ] **Step 1: Criar diretório e arquivo SQL**

Criar `backend/sql/03_paineis.sql` com o conteúdo:

```sql
-- ── Variáveis (filtros reutilizáveis) ─────────────────────────

CREATE TABLE variaveis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    tipo          VARCHAR(30) NOT NULL,
    query_fonte   TEXT,
    param_names   TEXT[],
    ativo         BOOLEAN DEFAULT true,
    criado_em     TIMESTAMP DEFAULT NOW()
);

-- ── Painéis ───────────────────────────────────────────────────

CREATE TABLE paineis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    icone         VARCHAR(50) DEFAULT 'chart-bar',
    colunas       INTEGER NOT NULL DEFAULT 3,
    linhas_fixas  BOOLEAN DEFAULT false,
    total_linhas  INTEGER,
    empresa_id    INTEGER REFERENCES empresas(id) NULL,
    ativo         BOOLEAN DEFAULT true,
    ordem_menu    INTEGER DEFAULT 0,
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- ── Indicadores dentro do painel ─────────────────────────────

CREATE TABLE painel_indicadores (
    id              SERIAL PRIMARY KEY,
    painel_id       INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    query_slug      VARCHAR(100) NOT NULL,
    titulo          VARCHAR(150),
    linha           INTEGER NOT NULL,
    coluna          INTEGER NOT NULL,
    col_span        INTEGER DEFAULT 1,
    row_span        INTEGER DEFAULT 1,
    posicao         INTEGER DEFAULT 0,
    UNIQUE (painel_id, linha, coluna)
);

-- ── Variáveis ativas em cada painel (filtros) ─────────────────

CREATE TABLE painel_variaveis (
    id            SERIAL PRIMARY KEY,
    painel_id     INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    variavel_id   INTEGER REFERENCES variaveis(id),
    obrigatorio   BOOLEAN DEFAULT false,
    valor_padrao  TEXT,
    posicao       INTEGER DEFAULT 0,
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

INSERT INTO painel_indicadores (painel_id, query_slug, linha, coluna, col_span, titulo)
VALUES
  (1, 'kpi_receita',          1, 1, 1, NULL),
  (1, 'kpi_pedidos',          1, 2, 1, NULL),
  (1, 'kpi_ticket_medio',     1, 3, 1, NULL),
  (1, 'kpi_clientes',         1, 4, 1, NULL),
  (1, 'chart_receita_mensal', 2, 1, 2, NULL),
  (1, 'chart_pedidos_status', 2, 3, 2, NULL),
  (1, 'table_pedidos_recentes',3, 1, 4, NULL);

INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
VALUES (1, 1, false, 1);

INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES (1, 1);
```

- [ ] **Step 2: Executar no banco**

```bash
docker exec -i datahub_postgres psql -U postgres -d datahub_meta < backend/sql/03_paineis.sql
```

Esperado: nenhum erro. Se der `already exists`, o SQL já foi aplicado.

- [ ] **Step 3: Verificar tabelas criadas**

```bash
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "\dt variaveis paineis painel_indicadores painel_variaveis painel_usuarios"
```

Esperado: 5 tabelas listadas.

---

## Task 2: Backend — `backend/routes/variaveis.py`

**Files:**
- Create: `backend/routes/variaveis.py`

**Interfaces:**
- Consumes: `query_meta` de `config.databases`, `get_current_user`/`require_admin` de `middleware.auth`, `query_company` de `config.databases`
- Produces: router em `variaveis.router` para `app.include_router()`

- [ ] **Step 1: Criar `backend/routes/variaveis.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta

router = APIRouter(prefix="/api/variaveis", tags=["Variáveis"])

TIPOS_VALIDOS = {'date', 'date_range', 'select', 'multiselect', 'text', 'number'}


class VariavelInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    tipo: str
    query_fonte: Optional[str] = None
    param_names: List[str] = []
    ativo: bool = True


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
async def atualizar_variavel(variavel_id: int, body: dict, user=Depends(require_admin)):
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


@router.get("/executar-fonte/{variavel_id}")
async def executar_fonte_variavel(variavel_id: int, user=Depends(get_current_user)):
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

**Atenção:** A rota `/executar-fonte/{variavel_id}` é GET (não POST como no spec original), pois o `api.js` chama sem `method`. Também deve vir ANTES de `/{variavel_id}` para não ser interceptada como ID inteiro — mas como `executar-fonte` não é um inteiro, FastAPI resolve corretamente com `int` type hint. Mesmo assim, declare-a antes para clareza.

- [ ] **Step 2: Verificar (após Task 3 registrar no main.py)**

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/variaveis/
```

Esperado: lista com as 3 variáveis seed (`periodo`, `data_unica`, `texto_livre`).

---

## Task 3: Backend — `backend/routes/paineis.py` + registrar no `main.py`

**Files:**
- Create: `backend/routes/paineis.py`
- Modify: `backend/main.py` (2 linhas)

**Interfaces:**
- Consumes: `query_meta` de `config.databases`, `get_current_user`/`require_admin` de `middleware.auth`, `resolver_query` de `services.query_runner`
- Produces: `paineis.router` com prefixo `/api/paineis`

- [ ] **Step 1: Criar `backend/routes/paineis.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
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


# ── Rotas estáticas ANTES das dinâmicas ──────────────────────

@router.get("/meu-menu")
async def meu_menu(user=Depends(get_current_user)):
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


@router.get("/slug/{slug}")
async def buscar_painel_por_slug(slug: str, user=Depends(get_current_user)):
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


# ── CRUD Painéis ─────────────────────────────────────────────

@router.get("/")
async def listar_paineis(user=Depends(get_current_user)):
    if user["role"] == "admin":
        rows = await query_meta("SELECT * FROM paineis ORDER BY ordem_menu, nome")
    else:
        rows = await query_meta("""
            SELECT p.* FROM paineis p
            JOIN painel_usuarios pu ON pu.painel_id = p.id
            WHERE pu.usuario_id = $1 AND p.ativo = true
            ORDER BY p.ordem_menu, p.nome
        """, user["id"])
    return [dict(r) for r in rows]


@router.get("/{painel_id}")
async def buscar_painel(painel_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not rows:
        raise HTTPException(404, "Painel não encontrado")
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
async def atualizar_painel(painel_id: int, body: dict, user=Depends(require_admin)):
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
        LEFT JOIN queries q ON q.slug = pi.query_slug
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
    """, painel_id)
    return [dict(r) for r in rows]


@router.post("/{painel_id}/indicadores")
async def adicionar_indicador(painel_id: int, body: IndicadorInput, user=Depends(require_admin)):
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
async def salvar_indicadores(painel_id: int, indicadores: List[IndicadorInput], user=Depends(require_admin)):
    await query_meta("DELETE FROM painel_indicadores WHERE painel_id = $1", painel_id)
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
async def remover_indicador(painel_id: int, indicador_id: int, user=Depends(require_admin)):
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
async def salvar_variaveis_painel(painel_id: int, variaveis: List[VariavelPainelInput], user=Depends(require_admin)):
    await query_meta("DELETE FROM painel_variaveis WHERE painel_id = $1", painel_id)
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
async def salvar_usuarios_painel(painel_id: int, usuario_ids: List[int], user=Depends(require_admin)):
    await query_meta("DELETE FROM painel_usuarios WHERE painel_id = $1", painel_id)
    for uid in usuario_ids:
        await query_meta(
            "INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES ($1, $2)",
            painel_id, uid
        )
    return {"ok": True, "usuarios": usuario_ids}


# ── Renderizar painel completo ────────────────────────────────

@router.get("/{painel_id}/renderizar")
async def renderizar_painel(painel_id: int, request: Request, user=Depends(get_current_user)):
    """
    Executa todas as queries do painel com os filtros aplicados.
    Filtros chegam como query params: ?data_inicio=2026-01-01&data_fim=2026-06-30
    """
    from services.query_runner import resolver_query

    filtros = dict(request.query_params)

    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        raise HTTPException(404, "Painel não encontrado")

    indicadores = await query_meta("""
        SELECT * FROM painel_indicadores
        WHERE painel_id = $1
        ORDER BY linha, coluna
    """, painel_id)

    resultado = []
    for ind in indicadores:
        ind_dict = dict(ind)
        try:
            dados = await resolver_query(
                slug=ind_dict["query_slug"],
                company_slug=user["company_slug"],
                empresa_id=user["empresa_id"],
                parametros=filtros
            )
            ind_dict["dados"] = dados.get("data")
            ind_dict["query_tipo"] = dados.get("tipo")
            ind_dict["erro"] = None
        except Exception as e:
            ind_dict["dados"] = None
            ind_dict["query_tipo"] = None
            ind_dict["erro"] = str(e)
        resultado.append(ind_dict)

    return {
        "painel": dict(painel_rows[0]),
        "indicadores": resultado
    }
```

- [ ] **Step 2: Registrar rotas no `backend/main.py`**

No import existente na linha 7:
```python
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios
```
Mudar para:
```python
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios, variaveis, paineis
```

Após a linha `app.include_router(usuarios.router)` (linha 29):
```python
app.include_router(variaveis.router)
app.include_router(paineis.router)
```

- [ ] **Step 3: Verificar endpoints básicos**

```bash
# Listar variáveis
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/variaveis/

# Menu do usuário
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/paineis/meu-menu

# Painel por slug
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/paineis/slug/visao_geral
```

Esperado: JSON válido; meu-menu retorna `[{"slug":"visao_geral","nome":"Visão Geral",...}]`.

---

## Task 4: Frontend — Adicionar métodos ao `api.js`

**Files:**
- Modify: `frontend/src/lib/api.js`

**Interfaces:**
- Consumes: endpoints `/api/variaveis/*` e `/api/paineis/*` do backend
- Produces: métodos `listarVariaveis`, `meuMenu`, `buscarPainelPorSlug`, `renderizarPainel`, etc.

- [ ] **Step 1: Adicionar métodos no final do objeto `api` em `frontend/src/lib/api.js`**

Antes do `};` final, adicionar:

```javascript
    // Variáveis
    listarVariaveis:        ()          => request('/api/variaveis/'),
    buscarVariavel:         (id)        => request(`/api/variaveis/${id}`),
    criarVariavel:          (d)         => request('/api/variaveis/', { method: 'POST', body: JSON.stringify(d) }),
    atualizarVariavel:      (id, d)     => request(`/api/variaveis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
    desativarVariavel:      (id)        => request(`/api/variaveis/${id}`, { method: 'DELETE' }),
    executarFonteVariavel:  (id)        => request(`/api/variaveis/executar-fonte/${id}`),

    // Painéis
    listarPaineis:          ()          => request('/api/paineis/'),
    meuMenu:                ()          => request('/api/paineis/meu-menu'),
    buscarPainel:           (id)        => request(`/api/paineis/${id}`),
    buscarPainelPorSlug:    (slug)      => request(`/api/paineis/slug/${slug}`),
    criarPainel:            (d)         => request('/api/paineis/', { method: 'POST', body: JSON.stringify(d) }),
    atualizarPainel:        (id, d)     => request(`/api/paineis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
    desativarPainel:        (id)        => request(`/api/paineis/${id}`, { method: 'DELETE' }),

    // Indicadores do painel
    indicadoresPainel:      (id)        => request(`/api/paineis/${id}/indicadores`),
    salvarIndicadores:      (id, d)     => request(`/api/paineis/${id}/indicadores`, { method: 'PUT', body: JSON.stringify(d) }),

    // Variáveis do painel
    variaveisPainel:        (id)        => request(`/api/paineis/${id}/variaveis`),
    salvarVariaveisPainel:  (id, d)     => request(`/api/paineis/${id}/variaveis`, { method: 'PUT', body: JSON.stringify(d) }),

    // Usuários do painel
    usuariosPainel:         (id)        => request(`/api/paineis/${id}/usuarios`),
    salvarUsuariosPainel:   (id, d)     => request(`/api/paineis/${id}/usuarios`, { method: 'PUT', body: JSON.stringify(d) }),

    // Renderização
    renderizarPainel: (id, filtros) => {
        const p = new URLSearchParams(filtros || {});
        return request(`/api/paineis/${id}/renderizar?${p}`);
    },
```

---

## Task 5: Frontend — Menu dinâmico no `+layout.svelte`

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`

**Interfaces:**
- Consumes: `api.meuMenu()` → `[{id, slug, nome, icone, ordem_menu}]`
- Produces: sidebar com seção "Meus Painéis" dinâmica + links admin para painéis/variáveis

- [ ] **Step 1: Adicionar estado e carregamento do menu no `<script>`**

Após `let sidebarOpen = true;`, adicionar:

```javascript
  let menuPaineis = [];

  async function carregarMenu() {
    try {
      menuPaineis = await api.meuMenu();
    } catch (e) {
      console.error('Erro ao carregar menu de painéis:', e);
    }
  }
```

No `onMount`, após `usuario.set(me)`, adicionar chamada ao `carregarMenu()`:

```javascript
        usuario.set(me);
        carregarMenu();   // ← adicionar esta linha
        if (!$empresaAtiva) {
```

- [ ] **Step 2: Atualizar `adminLinks` para incluir painéis e variáveis**

Localizar:
```javascript
  const adminLinks = [
    { href: '/configuracoes/empresas', label: 'Empresas'  },
    { href: '/configuracoes/usuarios', label: 'Usuários'  },
    { href: '/configuracoes/queries',  label: 'Queries'   },
  ];
```

Substituir por:
```javascript
  const adminLinks = [
    { href: '/configuracoes/paineis',   label: 'Painéis'   },
    { href: '/configuracoes/variaveis', label: 'Variáveis' },
    { href: '/configuracoes/queries',   label: 'Queries'   },
    { href: '/configuracoes/empresas',  label: 'Empresas'  },
    { href: '/configuracoes/usuarios',  label: 'Usuários'  },
  ];
```

- [ ] **Step 3: Adicionar seção "Meus Painéis" no template HTML**

Localizar no template:
```svelte
        {#each navLinks as link}
          <li class:active={isActive(link.href)}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}

        {#if $isAdmin}
```

Substituir por:
```svelte
        {#each navLinks as link}
          <li class:active={isActive(link.href)}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}

        {#if menuPaineis.length > 0}
          <li class="nav-section">Meus Painéis</li>
          {#each menuPaineis as painel}
            <li class:active={isActive(`/painel/${painel.slug}`)}>
              <a href="/painel/{painel.slug}">{painel.nome}</a>
            </li>
          {/each}
        {/if}

        {#if $isAdmin}
```

---

## Task 6: Frontend — Componente `FiltroVariavel.svelte`

**Files:**
- Create: `frontend/src/lib/components/FiltroVariavel.svelte`

**Interfaces:**
- Consumes: `variavel: {nome, tipo, param_names, variavel_id, query_fonte}`, `valor: {[param]: string}`
- Produces: evento `mudou` com `{[param]: value}` via `createEventDispatcher`

- [ ] **Step 1: Criar `frontend/src/lib/components/FiltroVariavel.svelte`**

```svelte
<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '$lib/api.js';

  export let variavel;
  export let valor = {};

  const dispatch = createEventDispatcher();
  let opcoes = [];

  onMount(async () => {
    if (variavel.tipo === 'select' || variavel.tipo === 'multiselect') {
      try {
        opcoes = await api.executarFonteVariavel(variavel.variavel_id);
      } catch (e) {
        console.error('Erro ao carregar opções:', e);
      }
    }
  });

  function emitir(params) {
    dispatch('mudou', params);
  }
</script>

<div class="filtro-item">
  <label class="filtro-label">{variavel.nome}</label>

  {#if variavel.tipo === 'date_range'}
    <input type="date"
      value={valor.data_inicio || ''}
      onchange={e => emitir({ data_inicio: e.target.value })}
    />
    <span class="filtro-sep">até</span>
    <input type="date"
      value={valor.data_fim || ''}
      onchange={e => emitir({ data_fim: e.target.value })}
    />

  {:else if variavel.tipo === 'date'}
    <input type="date"
      value={valor[variavel.param_names?.[0]] || ''}
      onchange={e => emitir({ [variavel.param_names[0]]: e.target.value })}
    />

  {:else if variavel.tipo === 'select'}
    <select onchange={e => emitir({ [variavel.param_names[0]]: e.target.value })}>
      <option value="">Todos</option>
      {#each opcoes as opt}
        <option value={opt.valor}>{opt.label}</option>
      {/each}
    </select>

  {:else if variavel.tipo === 'multiselect'}
    <select multiple onchange={e => {
      const vals = [...e.target.selectedOptions].map(o => o.value);
      emitir({ [variavel.param_names[0]]: vals.join(',') });
    }}>
      {#each opcoes as opt}
        <option value={opt.valor}>{opt.label}</option>
      {/each}
    </select>

  {:else if variavel.tipo === 'text'}
    <input type="text"
      placeholder="Buscar..."
      value={valor[variavel.param_names?.[0]] || ''}
      oninput={e => emitir({ [variavel.param_names[0]]: e.target.value })}
    />

  {:else if variavel.tipo === 'number'}
    <input type="number"
      value={valor[variavel.param_names?.[0]] || ''}
      oninput={e => emitir({ [variavel.param_names[0]]: e.target.value })}
    />
  {/if}
</div>

<style>
.filtro-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filtro-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.filtro-sep {
  font-size: 12px;
  color: var(--muted);
}
</style>
```

---

## Task 7: Frontend — Página `/painel/[slug]/+page.svelte`

**Files:**
- Create: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Consumes: `api.buscarPainelPorSlug(slug)`, `api.variaveisPainel(id)`, `api.renderizarPainel(id, filtros)`
- Consumes: componentes `KPICard`, `ChartPanel`, `DataTable`, `FiltroVariavel`
- Produces: página pública do painel com grid dinâmico

- [ ] **Step 1: Criar diretório e arquivo**

Criar `frontend/src/routes/painel/[slug]/+page.svelte`:

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
  let filtrosAtivos = {};
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try {
      painel = await api.buscarPainelPorSlug(slug);
      variaveis = await api.variaveisPainel(painel.id);

      variaveis.forEach(v => {
        if (v.valor_padrao && v.param_names?.length) {
          v.param_names.forEach(p => { filtrosAtivos[p] = v.valor_padrao; });
        }
      });

      await carregarDados();
    } catch (e) {
      erro = e.message;
      carregando = false;
    }
  });

  async function carregarDados() {
    carregando = true;
    erro = null;
    try {
      const resultado = await api.renderizarPainel(painel.id, filtrosAtivos);
      indicadores = resultado.indicadores;
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  }

  function onFiltroMudou(event) {
    filtrosAtivos = { ...filtrosAtivos, ...event.detail };
  }
</script>

<svelte:head><title>{painel?.nome ?? 'Painel'} — DataHub</title></svelte:head>

<div class="painel-page">
  {#if erro && !painel}
    <p class="error">{erro}</p>
  {:else if painel}
    <div class="painel-header">
      <h2>{painel.nome}</h2>
      {#if painel.descricao}
        <p class="descricao">{painel.descricao}</p>
      {/if}
    </div>

    {#if variaveis.length > 0}
      <div class="filtros-bar">
        {#each variaveis as variavel}
          <FiltroVariavel
            {variavel}
            valor={filtrosAtivos}
            on:mudou={onFiltroMudou}
          />
        {/each}
        <button class="btn-primary" onclick={carregarDados}>Aplicar</button>
      </div>
    {/if}

    {#if carregando}
      <div class="loading-grid">Carregando painel...</div>
    {:else if erro}
      <p class="error">{erro}</p>
    {:else}
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
              <p class="error" style="font-size:12px; padding:8px">{ind.erro}</p>

            {:else if ind.query_tipo === 'kpi'}
              <KPICard dados={ind.dados?.[0]} />

            {:else if ind.query_tipo?.startsWith('chart_')}
              <ChartPanel tipo={ind.query_tipo} dados={ind.dados} />

            {:else if ind.query_tipo === 'table'}
              <DataTable dados={ind.dados} />

            {:else}
              <p class="muted" style="font-size:12px; padding:8px">Tipo "{ind.query_tipo}" não suportado</p>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
.painel-page { padding: 24px; }
.painel-header { margin-bottom: 16px; }
.painel-header h2 { font-family: var(--font-display); font-size: 20px; color: var(--text); }
.descricao { color: var(--muted); font-size: 13px; margin-top: 4px; }

.filtros-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 20px;
}

.painel-grid {
  display: grid;
  gap: 16px;
}

.grid-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.card-titulo {
  padding: 12px 16px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  border-bottom: 1px solid var(--border);
}

.loading-grid {
  padding: 48px;
  text-align: center;
  color: var(--muted);
}

.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }
</style>
```

---

## Task 8: Frontend — Páginas `/configuracoes/variaveis`

**Files:**
- Create: `frontend/src/routes/configuracoes/variaveis/+page.svelte`
- Create: `frontend/src/routes/configuracoes/variaveis/nova/+page.svelte`

**Interfaces:**
- Consumes: `api.listarVariaveis()`, `api.criarVariavel(d)`, `api.desativarVariavel(id)`, `api.executarFonteVariavel(id)`

- [ ] **Step 1: Criar lista `frontend/src/routes/configuracoes/variaveis/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let variaveis   = [];
  let carregando  = true;
  let erro        = null;

  onMount(async () => {
    try {
      variaveis = await api.listarVariaveis();
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  async function desativar(v) {
    if (!confirm(`Desativar "${v.nome}"?`)) return;
    try {
      await api.desativarVariavel(v.id);
      variaveis = variaveis.filter(x => x.id !== v.id);
    } catch (e) {
      alert(e.message);
    }
  }

  const tipoLabel = {
    date: 'Data', date_range: 'Intervalo de datas',
    select: 'Seleção', multiselect: 'Multi-seleção',
    text: 'Texto', number: 'Número'
  };
</script>

<svelte:head><title>Variáveis — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Variáveis de Filtro</h2>
    <a href="/configuracoes/variaveis/nova" class="btn-primary">+ Nova Variável</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Slug</th>
          <th>Nome</th>
          <th>Tipo</th>
          <th>Parâmetros</th>
          <th>Query Fonte</th>
          <th>Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each variaveis as v}
          <tr>
            <td class="mono">{v.slug}</td>
            <td>{v.nome}</td>
            <td><span class="badge">{tipoLabel[v.tipo] || v.tipo}</span></td>
            <td class="mono small">{v.param_names?.join(', ') || '—'}</td>
            <td class="small">{v.query_fonte ? '✓ Sim' : '—'}</td>
            <td class="actions-cell">
              <button class="btn-ghost btn-sm danger" onclick={() => desativar(v)}>Desativar</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--muted); border-bottom: 1px solid var(--border); font-weight: 500; }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
.mono { font-family: var(--font-display); font-size: 12px; }
.small { font-size: 12px; color: var(--muted); }
.actions-cell { display: flex; gap: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
```

- [ ] **Step 2: Criar formulário `frontend/src/routes/configuracoes/variaveis/nova/+page.svelte`**

```svelte
<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let form = {
    slug: '', nome: '', descricao: '',
    tipo: 'date', query_fonte: '', param_names: [], ativo: true
  };

  let testando       = false;
  let resultadoTeste = null;
  let salvando       = false;
  let erro           = null;

  const tipos = [
    { value: 'date',        label: 'Data única' },
    { value: 'date_range',  label: 'Intervalo de datas' },
    { value: 'select',      label: 'Seleção (dropdown)' },
    { value: 'multiselect', label: 'Multi-seleção' },
    { value: 'text',        label: 'Texto livre' },
    { value: 'number',      label: 'Número' },
  ];

  const paramsPorTipo = {
    date:        ['data'],
    date_range:  ['data_inicio', 'data_fim'],
    select:      [],
    multiselect: [],
    text:        [],
    number:      [],
  };

  $: {
    const base = paramsPorTipo[form.tipo] || [];
    if (base.length > 0) {
      form.param_names = base;
    } else if (form.slug) {
      form.param_names = [form.slug];
    }
  }

  $: needsQuery = form.tipo === 'select' || form.tipo === 'multiselect';

  function gerarSlug(nome) {
    return nome.toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  }

  async function testarFonte() {
    if (!form.query_fonte) return;
    testando = true;
    resultadoTeste = null;
    try {
      const criada = await api.criarVariavel({ ...form, slug: form.slug || `_temp_${Date.now()}` });
      const resultado = await api.executarFonteVariavel(criada.id);
      await api.desativarVariavel(criada.id);
      resultadoTeste = { ok: true, linhas: resultado.length, amostra: resultado.slice(0, 5) };
    } catch (e) {
      resultadoTeste = { ok: false, erro: e.message };
    } finally {
      testando = false;
    }
  }

  async function salvar() {
    if (!form.nome) { erro = 'Nome é obrigatório.'; return; }
    if (!form.slug) { form.slug = gerarSlug(form.nome); }
    if (needsQuery && !form.query_fonte) { erro = 'Query fonte é obrigatória para este tipo.'; return; }
    erro = null;
    salvando = true;
    try {
      await api.criarVariavel(form);
      goto('/configuracoes/variaveis');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Variável — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <a href="/configuracoes/variaveis" class="back-link">← Voltar</a>
    <h2>Nova Variável de Filtro</h2>
  </div>

  <div class="form-card">
    <div class="field">
      <label>Nome</label>
      <input
        type="text"
        bind:value={form.nome}
        placeholder="ex: Período"
        oninput={() => { if (!form.slug) form.slug = gerarSlug(form.nome); }}
      />
    </div>

    <div class="field">
      <label>Slug</label>
      <input type="text" bind:value={form.slug} placeholder="ex: periodo" />
    </div>

    <div class="field">
      <label>Tipo</label>
      <select bind:value={form.tipo}>
        {#each tipos as t}
          <option value={t.value}>{t.label}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <label>Parâmetros gerados</label>
      <input type="text" value={form.param_names.join(', ')} readonly class="readonly" />
      <span class="hint">Preenchido automaticamente pelo tipo</span>
    </div>

    <div class="field">
      <label>Descrição</label>
      <input type="text" bind:value={form.descricao} placeholder="Descrição opcional" />
    </div>

    {#if needsQuery}
      <div class="field">
        <label>Query Fonte (SQL)</label>
        <span class="hint">Deve retornar colunas <code>valor</code> e <code>label</code></span>
        <textarea
          bind:value={form.query_fonte}
          rows="5"
          placeholder="SELECT id AS valor, nome AS label FROM tabela ORDER BY nome"
        ></textarea>
        <button class="btn-ghost" onclick={testarFonte} disabled={testando}>
          {testando ? 'Testando...' : 'Testar Query'}
        </button>

        {#if resultadoTeste}
          {#if resultadoTeste.ok}
            <div class="teste-ok">
              ✓ {resultadoTeste.linhas} opções encontradas.
              {#if resultadoTeste.amostra?.length}
                <table class="amostra-table">
                  <thead><tr><th>valor</th><th>label</th></tr></thead>
                  <tbody>
                    {#each resultadoTeste.amostra as row}
                      <tr><td>{row.valor}</td><td>{row.label}</td></tr>
                    {/each}
                  </tbody>
                </table>
              {/if}
            </div>
          {:else}
            <p class="error">{resultadoTeste.erro}</p>
          {/if}
        {/if}
      </div>
    {/if}

    {#if erro}
      <p class="error">{erro}</p>
    {/if}

    <div class="actions">
      <a href="/configuracoes/variaveis" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" onclick={salvar} disabled={salvando}>
        {salvando ? 'Salvando...' : 'Salvar Variável'}
      </button>
    </div>
  </div>
</div>

<style>
.page { padding: 24px; max-width: 640px; }
.page-header { margin-bottom: 24px; }
.back-link { color: var(--muted); font-size: 13px; display: block; margin-bottom: 8px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
label { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
input, select, textarea { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; }
textarea { resize: vertical; font-family: var(--font-display); }
.readonly { opacity: .6; cursor: default; }
.hint { font-size: 11px; color: var(--muted); }
.actions { display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.teste-ok { font-size: 12px; color: #3fb950; }
.amostra-table { margin-top: 8px; border-collapse: collapse; font-size: 12px; }
.amostra-table th, .amostra-table td { border: 1px solid var(--border); padding: 4px 8px; color: var(--text); }
</style>
```

---

## Task 9: Frontend — Páginas `/configuracoes/paineis`

**Files:**
- Create: `frontend/src/routes/configuracoes/paineis/+page.svelte`
- Create: `frontend/src/routes/configuracoes/paineis/novo/+page.svelte`

**Interfaces:**
- Consumes: `api.listarPaineis()`, `api.criarPainel(d)`, `api.desativarPainel(id)`, `api.salvarIndicadores(id,d)`, `api.salvarVariaveisPainel(id,d)`, `api.salvarUsuariosPainel(id,d)`, `api.listarQueries()`, `api.listarVariaveis()`, `api.listarUsuarios()`

- [ ] **Step 1: Criar lista `frontend/src/routes/configuracoes/paineis/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let paineis    = [];
  let carregando = true;
  let erro       = null;

  onMount(async () => {
    try {
      paineis = await api.listarPaineis();
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  async function desativar(p) {
    if (!confirm(`Desativar painel "${p.nome}"?`)) return;
    try {
      await api.desativarPainel(p.id);
      paineis = paineis.map(x => x.id === p.id ? { ...x, ativo: false } : x);
    } catch (e) {
      alert(e.message);
    }
  }
</script>

<svelte:head><title>Painéis — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Painéis</h2>
    <a href="/configuracoes/paineis/novo" class="btn-primary">+ Novo Painel</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else if paineis.length === 0}
    <p class="muted">Nenhum painel cadastrado.</p>
  {:else}
    <div class="cards-grid">
      {#each paineis as p}
        <div class="card" class:inativo={!p.ativo}>
          <div class="card-top">
            <span class="card-nome">{p.nome}</span>
            <span class="badge" class:ativo={p.ativo}>{p.ativo ? 'Ativo' : 'Inativo'}</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">slug: <code>{p.slug}</code></span>
            <span class="meta-item">{p.colunas} colunas</span>
            <span class="meta-item">{p.empresa_id ? `Empresa #${p.empresa_id}` : 'Global'}</span>
            {#if p.descricao}<span class="meta-descricao">{p.descricao}</span>{/if}
          </div>
          <div class="card-actions">
            <a href="/painel/{p.slug}" class="btn-ghost btn-sm" target="_blank">Ver painel</a>
            {#if p.ativo}
              <button class="btn-ghost btn-sm danger" onclick={() => desativar(p)}>Desativar</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.card.inativo { opacity: .5; }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; }
.card-nome { font-size: 15px; font-weight: 600; color: var(--text); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.badge.ativo { background: #1a4731; color: #3fb950; }
.card-meta { display: flex; flex-direction: column; gap: 4px; }
.meta-item { font-size: 12px; color: var(--muted); }
.meta-item code { font-family: var(--font-display); color: var(--accent-blue); }
.meta-descricao { font-size: 12px; color: var(--muted); font-style: italic; }
.card-actions { display: flex; gap: 8px; }
.danger { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

- [ ] **Step 2: Criar formulário `frontend/src/routes/configuracoes/paineis/novo/+page.svelte`**

```svelte
<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  // ── Estado ───────────────────────────────────────────────────
  let abaAtiva = 'geral';

  let form = {
    slug: '', nome: '', descricao: '', icone: 'chart-bar',
    colunas: 3, linhas_fixas: false, total_linhas: null,
    empresa_id: null, ativo: true, ordem_menu: 0
  };

  let indicadores  = [];   // {query_slug, titulo, linha, coluna, col_span, row_span, posicao}
  let varSelecionadas = []; // {variavel_id, obrigatorio, valor_padrao, posicao}
  let usuariosSelecionados = []; // [id]

  let queries      = [];
  let variaveis    = [];
  let usuarios     = [];
  let empresas     = [];
  let carregando   = true;
  let salvando     = false;
  let erro         = null;

  onMount(async () => {
    try {
      [queries, variaveis, usuarios, empresas] = await Promise.all([
        api.listarQueries(),
        api.listarVariaveis(),
        api.listarUsuarios(),
        api.listarEmpresas(),
      ]);
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  // ── Slug automático ──────────────────────────────────────────
  function gerarSlug(nome) {
    return nome.toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  }

  // ── Indicadores ──────────────────────────────────────────────
  function adicionarIndicador() {
    indicadores = [...indicadores, {
      query_slug: queries[0]?.slug || '', titulo: '',
      linha: indicadores.length + 1, coluna: 1,
      col_span: 1, row_span: 1, posicao: indicadores.length
    }];
  }

  function removerIndicador(i) {
    indicadores = indicadores.filter((_, idx) => idx !== i);
  }

  // ── Variáveis ────────────────────────────────────────────────
  function toggleVariavel(v) {
    const idx = varSelecionadas.findIndex(s => s.variavel_id === v.id);
    if (idx >= 0) {
      varSelecionadas = varSelecionadas.filter((_, i) => i !== idx);
    } else {
      varSelecionadas = [...varSelecionadas, {
        variavel_id: v.id, obrigatorio: false, valor_padrao: '', posicao: varSelecionadas.length
      }];
    }
  }

  function isVarSelecionada(id) {
    return varSelecionadas.some(s => s.variavel_id === id);
  }

  // ── Usuários ─────────────────────────────────────────────────
  function toggleUsuario(id) {
    if (usuariosSelecionados.includes(id)) {
      usuariosSelecionados = usuariosSelecionados.filter(x => x !== id);
    } else {
      usuariosSelecionados = [...usuariosSelecionados, id];
    }
  }

  // ── Salvar ───────────────────────────────────────────────────
  async function salvar() {
    if (!form.nome) { erro = 'Nome é obrigatório.'; return; }
    if (!form.slug) { form.slug = gerarSlug(form.nome); }
    erro = null;
    salvando = true;
    try {
      const painel = await api.criarPainel(form);
      if (indicadores.length > 0) {
        await api.salvarIndicadores(painel.id, indicadores);
      }
      if (varSelecionadas.length > 0) {
        await api.salvarVariaveisPainel(painel.id, varSelecionadas);
      }
      if (usuariosSelecionados.length > 0) {
        await api.salvarUsuariosPainel(painel.id, usuariosSelecionados);
      }
      goto('/configuracoes/paineis');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Novo Painel — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <a href="/configuracoes/paineis" class="back-link">← Voltar</a>
    <h2>Novo Painel</h2>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else}
    <!-- Abas -->
    <div class="tabs">
      <button class="tab" class:active={abaAtiva === 'geral'} onclick={() => abaAtiva = 'geral'}>
        Configurações Gerais
      </button>
      <button class="tab" class:active={abaAtiva === 'indicadores'} onclick={() => abaAtiva = 'indicadores'}>
        Indicadores ({indicadores.length})
      </button>
      <button class="tab" class:active={abaAtiva === 'acesso'} onclick={() => abaAtiva = 'acesso'}>
        Filtros e Acesso
      </button>
    </div>

    <!-- Aba 1: Geral -->
    {#if abaAtiva === 'geral'}
      <div class="form-card">
        <div class="field">
          <label>Nome do Painel</label>
          <input type="text" bind:value={form.nome}
            oninput={() => { if (!form.slug) form.slug = gerarSlug(form.nome); }}
            placeholder="ex: Visão Geral" />
        </div>
        <div class="field">
          <label>Slug</label>
          <input type="text" bind:value={form.slug} placeholder="ex: visao_geral" />
        </div>
        <div class="field">
          <label>Ícone</label>
          <input type="text" bind:value={form.icone} placeholder="chart-bar" />
          <span class="hint">Nome do ícone (usado no menu lateral)</span>
        </div>
        <div class="field">
          <label>Descrição</label>
          <input type="text" bind:value={form.descricao} placeholder="Opcional" />
        </div>
        <div class="field">
          <label>Empresa</label>
          <select bind:value={form.empresa_id}>
            <option value={null}>Global (todas as empresas)</option>
            {#each empresas as e}
              <option value={e.id}>{e.nome} ({e.slug})</option>
            {/each}
          </select>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Colunas do Grid</label>
            <input type="number" bind:value={form.colunas} min="1" max="12" />
          </div>
          <div class="field">
            <label>Ordem no Menu</label>
            <input type="number" bind:value={form.ordem_menu} min="0" />
          </div>
        </div>
        <div class="field">
          <label>Linhas</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" bind:group={form.linhas_fixas} value={false} /> Contínuas
            </label>
            <label class="radio-label">
              <input type="radio" bind:group={form.linhas_fixas} value={true} /> Fixas:
              {#if form.linhas_fixas}
                <input type="number" bind:value={form.total_linhas} min="1" style="width:60px; margin-left:8px" />
              {/if}
            </label>
          </div>
        </div>
      </div>
    {/if}

    <!-- Aba 2: Indicadores -->
    {#if abaAtiva === 'indicadores'}
      <div class="form-card">
        <div class="ind-layout">
          <!-- Editor de indicadores -->
          <div class="ind-editor">
            <button class="btn-ghost" onclick={adicionarIndicador}>+ Adicionar Indicador</button>
            {#if indicadores.length === 0}
              <p class="muted" style="margin-top:16px">Nenhum indicador adicionado.</p>
            {:else}
              {#each indicadores as ind, i}
                <div class="ind-item">
                  <div class="ind-row">
                    <div class="field flex-1">
                      <label>Query</label>
                      <select bind:value={ind.query_slug}>
                        {#each queries as q}
                          <option value={q.slug}>{q.nome} ({q.tipo})</option>
                        {/each}
                      </select>
                    </div>
                    <button class="btn-ghost btn-sm danger" onclick={() => removerIndicador(i)}>✕</button>
                  </div>
                  <div class="ind-row">
                    <div class="field flex-1">
                      <label>Título (opcional)</label>
                      <input type="text" bind:value={ind.titulo} placeholder="Override do título" />
                    </div>
                  </div>
                  <div class="ind-row grid-4">
                    <div class="field">
                      <label>Linha</label>
                      <input type="number" bind:value={ind.linha} min="1" />
                    </div>
                    <div class="field">
                      <label>Coluna</label>
                      <input type="number" bind:value={ind.coluna} min="1" />
                    </div>
                    <div class="field">
                      <label>Col Span</label>
                      <input type="number" bind:value={ind.col_span} min="1" max={form.colunas} />
                    </div>
                    <div class="field">
                      <label>Row Span</label>
                      <input type="number" bind:value={ind.row_span} min="1" />
                    </div>
                  </div>
                </div>
              {/each}
            {/if}
          </div>

          <!-- Preview do grid -->
          <div class="ind-preview">
            <div class="preview-label">Preview ({form.colunas} colunas)</div>
            <div class="preview-grid" style="grid-template-columns: repeat({form.colunas}, 1fr)">
              {#each indicadores as ind}
                <div class="preview-cell"
                  style="grid-column: {ind.coluna} / span {ind.col_span}; grid-row: {ind.linha} / span {ind.row_span}">
                  <span class="preview-slug">{ind.titulo || ind.query_slug}</span>
                </div>
              {/each}
            </div>
          </div>
        </div>
      </div>
    {/if}

    <!-- Aba 3: Filtros e Acesso -->
    {#if abaAtiva === 'acesso'}
      <div class="form-card">
        <div class="section-title">Variáveis de Filtro</div>
        {#each variaveis as v}
          <div class="access-row">
            <label class="check-label">
              <input type="checkbox"
                checked={isVarSelecionada(v.id)}
                onchange={() => toggleVariavel(v)}
              />
              <span>{v.nome}</span>
              <span class="badge">{v.tipo}</span>
            </label>
            {#if isVarSelecionada(v.id)}
              {@const sel = varSelecionadas.find(s => s.variavel_id === v.id)}
              <label class="check-label" style="margin-left:32px; font-size:12px">
                <input type="checkbox" bind:checked={sel.obrigatorio} /> Obrigatório
              </label>
              <div style="margin-left:32px; display:flex; gap:8px; align-items:center; margin-top:4px">
                <span style="font-size:12px; color:var(--muted)">Valor padrão:</span>
                <input type="text" bind:value={sel.valor_padrao} style="width:140px; font-size:12px" />
              </div>
            {/if}
          </div>
        {/each}

        <div class="section-title" style="margin-top:24px">Usuários com Acesso</div>
        {#each usuarios as u}
          <div class="access-row">
            <label class="check-label">
              <input type="checkbox"
                checked={usuariosSelecionados.includes(u.id)}
                onchange={() => toggleUsuario(u.id)}
              />
              <span>{u.nome}</span>
              <span class="badge">{u.role}</span>
              <span style="font-size:12px; color:var(--muted)">{u.email}</span>
            </label>
          </div>
        {/each}
      </div>
    {/if}

    {#if erro}
      <p class="error" style="margin-top:16px">{erro}</p>
    {/if}

    <div class="form-footer">
      <a href="/configuracoes/paineis" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" onclick={salvar} disabled={salvando}>
        {salvando ? 'Salvando...' : 'Salvar Painel'}
      </button>
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; max-width: 960px; }
.page-header { margin-bottom: 20px; }
.back-link { color: var(--muted); font-size: 13px; display: block; margin-bottom: 8px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }

.tabs { display: flex; gap: 2px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.tab { background: none; border: none; padding: 10px 16px; color: var(--muted); font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text); border-bottom-color: var(--accent-blue); }
.tab:hover { color: var(--text); }

.form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field.flex-1 { flex: 1; }
label { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
input, select { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; }
.field-row { display: flex; gap: 16px; }
.radio-group { display: flex; gap: 16px; align-items: center; }
.radio-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text); text-transform: none; letter-spacing: 0; font-weight: 400; cursor: pointer; }
.hint { font-size: 11px; color: var(--muted); }

.ind-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.ind-editor { display: flex; flex-direction: column; gap: 12px; }
.ind-item { border: 1px solid var(--border); border-radius: 6px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.ind-row { display: flex; align-items: flex-end; gap: 8px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.ind-preview { }
.preview-label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.preview-grid { display: grid; gap: 4px; min-height: 200px; }
.preview-cell { background: var(--surface2); border: 1px solid var(--border); border-radius: 4px; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 48px; }
.preview-slug { font-size: 11px; color: var(--muted); text-align: center; word-break: break-all; }

.section-title { font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px; }
.access-row { padding: 8px 0; border-bottom: 1px solid var(--border); }
.check-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }

.form-footer { display: flex; gap: 12px; justify-content: flex-end; margin-top: 20px; }
.danger { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

---

## Checklist Final (do spec)

- [ ] SQL executado sem erros no datahub_meta
- [ ] `GET /api/paineis/meu-menu` retorna painéis do usuário
- [ ] `GET /api/paineis/slug/visao_geral` retorna o painel de exemplo
- [ ] `GET /api/paineis/{id}/renderizar` retorna indicadores com dados
- [ ] Menu lateral carrega painéis dinamicamente após login
- [ ] Página `/painel/visao_geral` renderiza o grid corretamente
- [ ] Filtro de período recarrega os indicadores ao aplicar
- [ ] Admin vê links de Painéis e Variáveis no menu de configurações
- [ ] Formulário de novo painel salva com indicadores e filtros
- [ ] Formulário de nova variável com tipo select testa query_fonte
- [ ] Usuários sem acesso não veem o painel no menu
- [ ] Painel empresa-específica só aparece para usuários daquela empresa
