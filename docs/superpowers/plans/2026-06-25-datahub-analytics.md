# DataHub Analytics — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o sistema completo de analytics multiempresa DataHub — backend FastAPI com queries dinâmicas, worker ARQ e frontend SvelteKit com dashboard configurável.

**Architecture:** Backend Python/FastAPI com pool asyncpg por empresa, cache Redis e motor de queries dinâmicas; banco central `datahub_meta` com credenciais das empresas; frontend SvelteKit com dashboard totalmente configurável via tabela `queries` no banco.

**Tech Stack:** Python 3.12 + FastAPI + asyncpg + Redis (ARQ + cache) + Groq LLaMA 3.3 70B + SvelteKit + ECharts + Leaflet + Docker Compose

## Global Constraints

- Banco de dados local usa serviço `postgres` (hostname Docker) — não `172.17.0.1` (produção)
- `.env.dev` já existe com valores reais — todos os módulos lêem via `config/settings.py`
- Tabela de pedidos em cada empresa: `pedidos` com colunas `id, cliente_nome, produto, valor, status, canal, data`
- Empresas: `alpha` (Empresa Alpha Ltda), `beta` (Beta Comércio S.A.), `gamma` (Gamma Tech ME)
- Senha admin de teste: `admin123` — hash bcrypt já inserido no `scripts/init-db.sql`
- Nunca usar `import *` — sempre imports explícitos
- Todas as rotas FastAPI têm `try/except` e retornam HTTP 500 com mensagem descritiva
- `require_admin` é um segundo dependency de auth (role == 'admin') — definir em `middleware/auth.py`
- `build_context(company_slug, empresa_id)` — a versão dinâmica do RAG requer dois argumentos; `routes/ai.py` deve passar ambos
- Frontend usa `.js` (não `.ts`) conforme especificado no `arquitetura-stack-final.md`
- Nenhum teste automatizado é exigido pelo PROMPT.md — verificação manual via `/docs` e browser

---

## Mapeamento de Arquivos

### Backend (criar)
- `backend/config/__init__.py` — vazio
- `backend/config/settings.py` — Pydantic BaseSettings
- `backend/config/databases.py` — pools asyncpg (meta + por empresa)
- `backend/config/redis.py` — cliente Redis singleton
- `backend/services/__init__.py` — vazio
- `backend/services/cache.py` — helpers get/set/del cache
- `backend/services/groq_client.py` — cliente Groq async
- `backend/services/query_runner.py` — motor de queries dinâmicas + validar_sql
- `backend/services/rag.py` — RAG dinâmico via query_runner
- `backend/middleware/__init__.py` — vazio
- `backend/middleware/auth.py` — get_current_user + require_admin
- `backend/routes/__init__.py` — vazio
- `backend/routes/auth.py` — login/me/logout
- `backend/routes/queries.py` — CRUD queries + testar + executar + layout
- `backend/routes/charts.py` — wrapper dinâmico para charts/{slug}
- `backend/routes/tables.py` — listagem paginada de pedidos
- `backend/routes/ai.py` — chatbot RAG + histórico
- `backend/routes/reports.py` — solicitar/status/resultado relatórios
- `backend/main.py` — app FastAPI com startup/shutdown
- `backend/worker.py` — ARQ worker completo
- `backend/.env.example` — template de variáveis
- `backend/.gitignore` — ignora .env e caches

### Frontend (criar)
- `frontend/src/app.css` — design system (variáveis CSS + estilos base)
- `frontend/src/lib/api.js` — todos os métodos de API
- `frontend/src/lib/stores/company.js` — stores Svelte globais
- `frontend/src/lib/components/KPICard.svelte` — card de KPI único
- `frontend/src/lib/components/ChartPanel.svelte` — wrapper ECharts multi-tipo
- `frontend/src/lib/components/MapPanel.svelte` — mapa Leaflet dark
- `frontend/src/lib/components/DataTable.svelte` — tabela paginada
- `frontend/src/lib/components/AIChat.svelte` — chat com histórico
- `frontend/src/lib/components/QueryEditor.svelte` — editor SQL com validação de contrato
- `frontend/src/routes/+layout.svelte` — sidebar + topbar + guard de auth
- `frontend/src/routes/+page.svelte` — dashboard dinâmico
- `frontend/src/routes/login/+page.svelte` — tela de login
- `frontend/src/routes/ai/+page.svelte` — página do chatbot
- `frontend/src/routes/configuracoes/queries/+page.svelte` — lista de queries
- `frontend/src/routes/configuracoes/queries/nova/+page.svelte` — criar query
- `frontend/Dockerfile` — build multi-stage (node → nginx)
- `frontend/nginx.conf` — serve SPA + proxy /api/
- `frontend/.env.example` — template VITE_API_URL

### Raiz (criar)
- `.gitignore` — root gitignore
- `README.md` — documentação do projeto

---

## Task 1: Backend — Camada de Config

**Files:**
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/databases.py`
- Create: `backend/config/redis.py`

**Interfaces:**
- Produces: `settings` (instância global), `get_meta_pool()`, `get_company_pool(slug)`, `query_company(slug, sql, *args)`, `query_meta(sql, *args)`, `get_redis()`

- [ ] **Step 1: Criar pasta config e arquivo __init__.py vazio**

```bash
# No Windows (PowerShell ou via Docker):
# Criar os arquivos manualmente com o Write tool
```

Criar `backend/config/__init__.py` (vazio).

- [ ] **Step 2: Criar backend/config/settings.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PORT: int = 3001
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 480

    META_DB_HOST: str = "postgres"
    META_DB_PORT: int = 5432
    META_DB_NAME: str = "datahub_meta"
    META_DB_USER: str = "datahub_user"
    META_DB_PASS: str

    REDIS_URL: str = "redis://redis:6379"
    GROQ_API_KEY: str
    FRONTEND_URL: str = "*"

    class Config:
        env_file = ".env.dev"
        env_file_encoding = "utf-8"

settings = Settings()
```

- [ ] **Step 3: Criar backend/config/databases.py**

```python
import asyncpg
from typing import Dict, Optional
from config.settings import settings

_meta_pool: Optional[asyncpg.Pool] = None
_company_pools: Dict[str, asyncpg.Pool] = {}


async def get_meta_pool() -> asyncpg.Pool:
    global _meta_pool
    if _meta_pool is None:
        _meta_pool = await asyncpg.create_pool(
            host=settings.META_DB_HOST,
            port=settings.META_DB_PORT,
            database=settings.META_DB_NAME,
            user=settings.META_DB_USER,
            password=settings.META_DB_PASS,
            min_size=2,
            max_size=10,
        )
    return _meta_pool


async def get_company_pool(company_slug: str) -> asyncpg.Pool:
    if company_slug in _company_pools:
        return _company_pools[company_slug]

    meta = await get_meta_pool()
    async with meta.acquire() as conn:
        empresa = await conn.fetchrow(
            "SELECT * FROM empresas WHERE slug = $1 AND ativo = true",
            company_slug
        )

    if not empresa:
        raise ValueError(f"Empresa '{company_slug}' não encontrada ou inativa")

    pool = await asyncpg.create_pool(
        host=empresa["db_host"],
        port=empresa["db_port"],
        database=empresa["db_name"],
        user=empresa["db_user"],
        password=empresa["db_pass"],
        min_size=2,
        max_size=10,
    )
    _company_pools[company_slug] = pool
    return pool


async def query_company(company_slug: str, sql: str, *args):
    pool = await get_company_pool(company_slug)
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def query_meta(sql: str, *args):
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def close_all_pools():
    global _meta_pool, _company_pools
    if _meta_pool:
        await _meta_pool.close()
        _meta_pool = None
    for pool in _company_pools.values():
        await pool.close()
    _company_pools.clear()
```

- [ ] **Step 4: Criar backend/config/redis.py**

```python
import redis.asyncio as aioredis
from config.settings import settings

_redis = None


async def get_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis
```

- [ ] **Step 5: Verificar importações rodando no container**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from config.settings import settings; print(settings.META_DB_NAME)"
```
Esperado: `datahub_meta`

---

## Task 2: Backend — Services (cache + groq + query_runner)

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/cache.py`
- Create: `backend/services/groq_client.py`
- Create: `backend/services/query_runner.py`

**Interfaces:**
- Consumes: `get_redis()` de `config/redis.py`, `query_meta()` e `query_company()` de `config/databases.py`
- Produces: `cache_get(key)`, `cache_set(key, data, ttl)`, `cache_del_prefix(prefix)`, `ask(question, context, company_name)`, `resolver_query(slug, company_slug, empresa_id, parametros)`, `invalidar_cache_empresa(company_slug)`, `validar_sql(sql)`

- [ ] **Step 1: Criar backend/services/__init__.py (vazio)**

- [ ] **Step 2: Criar backend/services/cache.py**

```python
import json
from config.redis import get_redis

TTL_KPIS    = 300
TTL_CHARTS  = 600
TTL_MONTHLY = 3600


async def cache_get(key: str):
    redis = await get_redis()
    val = await redis.get(key)
    return json.loads(val) if val else None


async def cache_set(key: str, data, ttl: int = TTL_KPIS):
    redis = await get_redis()
    await redis.setex(key, ttl, json.dumps(data, default=str))


async def cache_del_prefix(prefix: str):
    redis = await get_redis()
    keys = await redis.keys(f"{prefix}*")
    if keys:
        await redis.delete(*keys)
```

- [ ] **Step 3: Criar backend/services/groq_client.py**

```python
from groq import AsyncGroq
from config.settings import settings

client = AsyncGroq(api_key=settings.GROQ_API_KEY)


async def ask(question: str, context: str, company_name: str) -> str:
    system_prompt = f"""Você é um assistente de analytics de negócios da empresa "{company_name}".
Responda SEMPRE em português, de forma direta e objetiva (máx 3 parágrafos).
Use APENAS os dados abaixo para fundamentar suas respostas. Não invente números.
Se os dados não forem suficientes para responder, diga claramente.

DADOS ATUAIS DA EMPRESA:
{context}"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1000,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": question}
        ]
    )
    return response.choices[0].message.content
```

- [ ] **Step 4: Criar backend/services/query_runner.py**

```python
"""Motor de execução de queries dinâmicas com cache e validação SQL."""
import json
from config.databases import query_meta, query_company
from services.cache import cache_get, cache_set

PALAVRAS_PROIBIDAS = [
    'drop', 'truncate', 'delete', 'insert', 'update',
    'alter', 'create', 'grant', 'revoke', 'pg_', 'information_schema'
]


def validar_sql(sql: str) -> bool:
    sql_lower = sql.lower().strip()
    if not sql_lower.startswith('select'):
        raise ValueError("Apenas queries SELECT são permitidas")
    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in sql_lower:
            raise ValueError(f"Palavra não permitida: '{palavra}'")
    return True


async def resolver_query(
    slug: str,
    company_slug: str,
    empresa_id: int,
    parametros: dict = {}
) -> dict:
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

    params_key = json.dumps(parametros, sort_keys=True)
    cache_key = f"query:{slug}:{company_slug}:{params_key}"

    if query["cache_ttl"] > 0:
        cached = await cache_get(cache_key)
        if cached:
            return {"data": cached, "from_cache": True, "query": query["nome"], "tipo": query["tipo"]}

    sql = query["sql_texto"]

    param_rows = await query_meta(
        "SELECT * FROM query_parametros WHERE query_id = $1 ORDER BY id",
        query["id"]
    )

    valores = []
    for p in param_rows:
        val = parametros.get(p["nome"], p["valor_padrao"])
        if val is None and p["obrigatorio"]:
            raise ValueError(f"Parâmetro obrigatório ausente: {p['nome']}")
        valores.append(val)

    resultado = await query_company(company_slug, sql, *valores)
    data = [dict(r) for r in resultado]

    if query["cache_ttl"] > 0:
        await cache_set(cache_key, data, ttl=query["cache_ttl"])

    return {
        "data": data,
        "from_cache": False,
        "query": query["nome"],
        "tipo": query["tipo"]
    }


async def invalidar_cache_empresa(company_slug: str):
    from config.redis import get_redis
    redis = await get_redis()
    keys = await redis.keys(f"query:*:{company_slug}:*")
    if keys:
        await redis.delete(*keys)
```

- [ ] **Step 5: Verificar sintaxe**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from services.cache import cache_get; from services.query_runner import validar_sql; print('ok')"
```
Esperado: `ok`

---

## Task 3: Backend — Service RAG (dinâmico)

**Files:**
- Create: `backend/services/rag.py`

**Interfaces:**
- Consumes: `query_meta()`, `resolver_query(slug, company_slug, empresa_id)`
- Produces: `build_context(company_slug: str, empresa_id: int) -> str`

- [ ] **Step 1: Criar backend/services/rag.py**

```python
"""RAG dinâmico: executa queries do tipo rag_context cadastradas no datahub_meta."""
import json
from config.databases import query_meta
from services.query_runner import resolver_query


async def build_context(company_slug: str, empresa_id: int) -> str:
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
            partes.append(
                f"[{q['nome']}]:\n{json.dumps(resultado['data'], default=str, ensure_ascii=False)}"
            )
        except Exception as e:
            partes.append(f"[{q['nome']}]: erro ao buscar dados ({e})")

    return "\n\n".join(partes)
```

- [ ] **Step 2: Verificar sintaxe**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from services.rag import build_context; print('ok')"
```
Esperado: `ok`

---

## Task 4: Backend — Middleware de Auth

**Files:**
- Create: `backend/middleware/__init__.py`
- Create: `backend/middleware/auth.py`

**Interfaces:**
- Produces: `get_current_user` (FastAPI Dependency), `require_admin` (FastAPI Dependency)
- Payload JWT: `{user_id: int, company_slug: str}`
- Retorno dict: `{id, nome, role, empresa_id, company_slug, company_name}`

- [ ] **Step 1: Criar backend/middleware/__init__.py (vazio)**

- [ ] **Step 2: Criar backend/middleware/auth.py**

```python
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from config.settings import settings
from config.databases import query_meta

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    rows = await query_meta("""
        SELECT u.id, u.nome, u.role,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.slug = $2 AND u.ativo = true AND e.ativo = true
    """, payload["user_id"], payload["company_slug"])

    if not rows:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return dict(rows[0])


async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Requer perfil admin")
    return user
```

- [ ] **Step 3: Verificar sintaxe**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from middleware.auth import get_current_user, require_admin; print('ok')"
```
Esperado: `ok`

---

## Task 5: Backend — Rota de Auth (login/me/logout)

**Files:**
- Create: `backend/routes/__init__.py`
- Create: `backend/routes/auth.py`

**Interfaces:**
- Consumes: `query_meta()`, `settings.JWT_SECRET`, `get_redis()`
- Produces: `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`

- [ ] **Step 1: Criar backend/routes/__init__.py (vazio)**

- [ ] **Step 2: Criar backend/routes/auth.py**

```python
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
import bcrypt
from config.settings import settings
from config.databases import query_meta
from config.redis import get_redis
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginInput(BaseModel):
    email: str
    senha: str
    company_slug: str


@router.post("/login")
async def login(body: LoginInput):
    try:
        rows = await query_meta(
            "SELECT * FROM usuarios WHERE email = $1 AND ativo = true",
            body.email
        )
        if not rows:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        usuario = dict(rows[0])

        if not bcrypt.checkpw(body.senha.encode(), usuario["senha_hash"].encode()):
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Verifica acesso à empresa
        acesso = await query_meta("""
            SELECT e.id FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.slug = $2 AND e.ativo = true
        """, usuario["id"], body.company_slug)

        if not acesso:
            raise HTTPException(status_code=403, detail="Sem acesso a esta empresa")

        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        token = jwt.encode(
            {"user_id": usuario["id"], "company_slug": body.company_slug, "exp": expire},
            settings.JWT_SECRET,
            algorithm="HS256"
        )

        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no login: {e}")


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    try:
        redis = await get_redis()
        await redis.setex(f"blacklist:{user['id']}", settings.JWT_EXPIRE_MINUTES * 60, "1")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no logout: {e}")
```

- [ ] **Step 3: Verificar sintaxe**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from routes.auth import router; print('ok')"
```
Esperado: `ok`

---

## Task 6: Backend — Rota de Queries (CRUD + executar + layout)

**Files:**
- Create: `backend/routes/queries.py`

**Interfaces:**
- Consumes: `get_current_user`, `require_admin`, `query_meta()`, `query_company()`, `resolver_query()`, `invalidar_cache_empresa()`, `validar_sql()`
- Produces: `GET /api/queries/`, `GET /api/queries/{id}`, `POST /api/queries/`, `PATCH /api/queries/{id}`, `DELETE /api/queries/{id}`, `POST /api/queries/testar`, `GET /api/queries/executar/{slug}`, `GET /api/queries/layout/dashboard`

- [ ] **Step 1: Criar backend/routes/queries.py**

```python
from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from pydantic import BaseModel
from typing import Optional
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta, query_company
from services.query_runner import resolver_query, invalidar_cache_empresa, validar_sql

router = APIRouter(prefix="/api/queries", tags=["Queries"])


class QueryInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    sql_texto: str
    tipo: str
    empresa_id: Optional[int] = None
    cache_ttl: int = 300
    ativo: bool = True


class QueryUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    sql_texto: Optional[str] = None
    tipo: Optional[str] = None
    cache_ttl: Optional[int] = None
    ativo: Optional[bool] = None


TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context'
}


@router.get("/layout/dashboard")
async def layout_dashboard(user=Depends(get_current_user)):
    try:
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

        layout = sorted([dict(r) for r in rows], key=lambda x: x["posicao"])
        return layout
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar layout: {e}")


@router.get("/executar/{slug}")
async def executar_query(slug: str, user=Depends(get_current_user)):
    try:
        return await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar query: {e}")


@router.get("/")
async def listar_queries(
    tipo: Optional[str] = None,
    empresa_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar queries: {e}")


@router.get("/{query_id}")
async def buscar_query(query_id: int, user=Depends(get_current_user)):
    rows = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Query não encontrada")
    return dict(rows[0])


@router.post("/")
async def criar_query(body: QueryInput, user=Depends(require_admin)):
    try:
        if body.tipo not in TIPOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {TIPOS_VALIDOS}")
        validar_sql(body.sql_texto)

        rows = await query_meta("""
            INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo)
        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar query: {e}")


@router.patch("/{query_id}")
async def atualizar_query(query_id: int, body: QueryUpdate, user=Depends(require_admin)):
    try:
        atual = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
        if not atual:
            raise HTTPException(status_code=404, detail="Query não encontrada")

        atual = dict(atual[0])
        updates = body.dict(exclude_none=True)

        if not updates:
            return atual

        if "sql_texto" in updates:
            validar_sql(updates["sql_texto"])

        campos = []
        valores = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            campos.append(f"{k} = ${i}")
            valores.append(v)

        valores.append(query_id)
        sql = f"UPDATE queries SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
        rows = await query_meta(sql, *valores)

        if atual.get("empresa_id"):
            emp = await query_meta("SELECT slug FROM empresas WHERE id = $1", atual["empresa_id"])
            if emp:
                await invalidar_cache_empresa(emp[0]["slug"])

        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar query: {e}")


@router.delete("/{query_id}")
async def deletar_query(query_id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "DELETE FROM queries WHERE id = $1 RETURNING id, slug", query_id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Query não encontrada")
    return {"deletado": True, "slug": rows[0]["slug"]}


@router.post("/testar")
async def testar_query(body: QueryInput, user=Depends(require_admin)):
    try:
        validar_sql(body.sql_texto)
        resultado = await query_company(user["company_slug"], body.sql_texto)
        data = [dict(r) for r in resultado[:50]]
        return {
            "ok": True,
            "linhas": len(data),
            "colunas": list(data[0].keys()) if data else [],
            "amostra": data[:5]
        }
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
```

- [ ] **Step 2: Verificar sintaxe**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from routes.queries import router; print('ok')"
```
Esperado: `ok`

---

## Task 7: Backend — Rotas (charts, tables, ai, reports)

**Files:**
- Create: `backend/routes/charts.py`
- Create: `backend/routes/tables.py`
- Create: `backend/routes/ai.py`
- Create: `backend/routes/reports.py`

**Interfaces:**
- Produces: `GET /api/charts/{slug}`, `GET /api/tables/pedidos`, `POST /api/ai/ask`, `GET /api/ai/historico`, `POST /api/reports/solicitar`, `GET /api/reports/status/{id}`, `GET /api/reports/resultado/{id}`

- [ ] **Step 1: Criar backend/routes/charts.py (wrapper dinâmico)**

```python
from fastapi import APIRouter, Depends, Query as QueryParam
from typing import Optional
from middleware.auth import get_current_user
from services.query_runner import resolver_query
from fastapi import HTTPException

router = APIRouter(prefix="/api/charts", tags=["Charts"])


@router.get("/{slug}")
async def executar_chart(
    slug: str,
    data_inicio: Optional[str] = QueryParam(None),
    data_fim: Optional[str] = QueryParam(None),
    user=Depends(get_current_user)
):
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar chart: {e}")
```

- [ ] **Step 2: Criar backend/routes/tables.py**

```python
from fastapi import APIRouter, Depends, Query as QueryParam, HTTPException
from typing import Optional
from middleware.auth import get_current_user
from config.databases import query_company

router = APIRouter(prefix="/api/tables", tags=["Tables"])


@router.get("/pedidos")
async def listar_pedidos(
    page: int = QueryParam(1, ge=1),
    limit: int = QueryParam(20, ge=1, le=100),
    status: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    user=Depends(get_current_user)
):
    try:
        filtros = ["1=1"]
        params: list = []

        if status:
            params.append(status)
            filtros.append(f"status = ${len(params)}")
        if data_inicio:
            params.append(data_inicio)
            filtros.append(f"data >= ${len(params)}::timestamp")
        if data_fim:
            params.append(data_fim)
            filtros.append(f"data <= ${len(params)}::timestamp")

        where = " AND ".join(filtros)

        count_rows = await query_company(
            user["company_slug"],
            f"SELECT COUNT(*) AS total FROM pedidos WHERE {where}",
            *params
        )
        total = count_rows[0]["total"]
        pages = (total + limit - 1) // limit

        offset = (page - 1) * limit
        params_page = params + [limit, offset]
        n = len(params)

        rows = await query_company(
            user["company_slug"],
            f"""SELECT id, cliente_nome, produto, valor, status, canal,
                       TO_CHAR(data, 'DD/MM/YYYY HH24:MI') AS data
                FROM pedidos WHERE {where}
                ORDER BY data DESC
                LIMIT ${n+1} OFFSET ${n+2}""",
            *params_page
        )

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar pedidos: {e}")
```

- [ ] **Step 3: Criar backend/routes/ai.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from services.rag import build_context
from services.groq_client import ask
from services.cache import cache_get, cache_set, TTL_CHARTS
from config.databases import query_meta
import json

router = APIRouter(prefix="/api/ai", tags=["IA"])


class PerguntaInput(BaseModel):
    pergunta: str


@router.post("/ask")
async def chatbot(body: PerguntaInput, user=Depends(get_current_user)):
    try:
        ctx_key = f"rag_context:{user['company_slug']}"
        context = await cache_get(ctx_key)
        if not context:
            context = await build_context(user["company_slug"], user["empresa_id"])
            await cache_set(ctx_key, context, ttl=TTL_CHARTS)
        elif not isinstance(context, str):
            context = json.dumps(context)

        resposta = await ask(body.pergunta, context, user["company_name"])

        await query_meta(
            """INSERT INTO chat_historico (usuario_id, empresa_id, pergunta, resposta)
               VALUES ($1, $2, $3, $4)""",
            user["id"], user["empresa_id"], body.pergunta, resposta
        )

        return {"resposta": resposta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no chatbot: {e}")


@router.get("/historico")
async def historico(limit: int = 20, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            """SELECT pergunta, resposta, criado_em
               FROM chat_historico
               WHERE usuario_id = $1 AND empresa_id = $2
               ORDER BY criado_em DESC LIMIT $3""",
            user["id"], user["empresa_id"], limit
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {e}")
```

- [ ] **Step 4: Criar backend/routes/reports.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from middleware.auth import get_current_user
from config.databases import query_meta
import uuid

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class SolicitarInput(BaseModel):
    tipo: str = "relatorio_mensal"


@router.post("/solicitar")
async def solicitar_relatorio(body: SolicitarInput, user=Depends(get_current_user)):
    try:
        rows = await query_meta("""
            INSERT INTO tarefas (tipo, empresa_id, usuario_id, status, payload)
            VALUES ($1, $2, $3, 'pendente', $4::jsonb)
            RETURNING id
        """, body.tipo, user["empresa_id"], user["id"],
            f'{{"company_slug": "{user["company_slug"]}"}}'
        )
        tarefa_id = str(rows[0]["id"])
        return {"tarefa_id": tarefa_id, "status": "pendente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao solicitar relatório: {e}")


@router.get("/status/{tarefa_id}")
async def status_relatorio(tarefa_id: str, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT id, status, criado_em, concluido_em FROM tarefas WHERE id = $1 AND empresa_id = $2",
            uuid.UUID(tarefa_id), user["empresa_id"]
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        return dict(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar status: {e}")


@router.get("/resultado/{tarefa_id}")
async def resultado_relatorio(tarefa_id: str, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT id, status, resultado FROM tarefas WHERE id = $1 AND empresa_id = $2",
            uuid.UUID(tarefa_id), user["empresa_id"]
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")
        row = dict(rows[0])
        if row["status"] != "ok":
            return {"status": row["status"], "resultado": None}
        return {"status": row["status"], "resultado": row["resultado"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar resultado: {e}")
```

- [ ] **Step 5: Verificar sintaxe de todas as rotas**

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -c "from routes.charts import router as r1; from routes.tables import router as r2; from routes.ai import router as r3; from routes.reports import router as r4; print('ok')"
```
Esperado: `ok`

---

## Task 8: Backend — main.py e worker.py completos

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/worker.py`

**Interfaces:**
- Consumes: todos os routers, `get_meta_pool()`, `get_redis()`, `close_all_pools()`
- Produces: app FastAPI com `/api/health`, `/docs`, todos os prefixos de rota

- [ ] **Step 1: Substituir backend/main.py**

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from config.databases import get_meta_pool, close_all_pools
from config.redis import get_redis
from routes import auth, charts, tables, ai, reports, queries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datahub")

app = FastAPI(title="DataHub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(charts.router)
app.include_router(tables.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(queries.router)


@app.on_event("startup")
async def startup():
    try:
        await get_meta_pool()
        logger.info("✓ Conectado ao datahub_meta")
    except Exception as e:
        logger.error(f"✗ Falha ao conectar datahub_meta: {e}")

    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("✓ Conectado ao Redis")
    except Exception as e:
        logger.error(f"✗ Falha ao conectar Redis: {e}")

    logger.info(f"DataHub API v1.0.0 rodando na porta {settings.PORT}")


@app.on_event("shutdown")
async def shutdown():
    await close_all_pools()
    logger.info("Pools fechados")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": "1.0.0"}
```

- [ ] **Step 2: Substituir backend/worker.py**

```python
"""ARQ Worker — processa tarefas pesadas em background."""
import json
import logging
from arq.connections import RedisSettings
from config.databases import query_company, query_meta
from config.settings import settings

logger = logging.getLogger("datahub.worker")


async def gerar_relatorio_mensal(ctx, empresa_id: int, company_slug: str, usuario_id: int):
    try:
        await query_meta(
            "UPDATE tarefas SET status='rodando' WHERE empresa_id=$1 AND usuario_id=$2 AND status='pendente'",
            empresa_id, usuario_id
        )

        rows = await query_company(company_slug, """
            SELECT
                TO_CHAR(data, 'YYYY-MM') AS mes,
                COUNT(*) AS pedidos,
                SUM(valor) AS receita,
                AVG(valor) AS ticket_medio
            FROM pedidos
            WHERE data >= NOW() - INTERVAL '12 months'
            GROUP BY 1 ORDER BY 1
        """)

        resultado = [dict(r) for r in rows]

        await query_meta(
            """UPDATE tarefas SET status='ok', resultado=$1::jsonb, concluido_em=NOW()
               WHERE empresa_id=$2 AND usuario_id=$3 AND status='rodando'""",
            json.dumps(resultado, default=str), empresa_id, usuario_id
        )
        return resultado

    except Exception as e:
        await query_meta(
            "UPDATE tarefas SET status='erro', resultado=$1::jsonb WHERE empresa_id=$2 AND usuario_id=$3",
            json.dumps({"erro": str(e)}), empresa_id, usuario_id
        )
        raise


async def startup(ctx):
    logger.info("Worker iniciado")


async def shutdown(ctx):
    logger.info("Worker encerrado")


class WorkerSettings:
    functions = [gerar_relatorio_mensal]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
```

- [ ] **Step 3: Subir o stack completo e verificar /docs**

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

Aguardar ~30s e acessar `http://localhost:3001/docs` — deve mostrar a documentação Swagger com todas as rotas.

- [ ] **Step 4: Testar health endpoint**

```bash
curl http://localhost:3001/api/health
```
Esperado: `{"ok":true,"version":"1.0.0"}`

- [ ] **Step 5: Testar login com admin**

```bash
curl -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123","company_slug":"alpha"}'
```
Esperado: JSON com campo `token`

---

## Task 9: Backend — Arquivos de suporte (.env.example, .gitignore)

**Files:**
- Create: `backend/.env.example`
- Create: `backend/.gitignore`

- [ ] **Step 1: Criar backend/.env.example**

```env
# Copie para .env.dev e preencha os valores reais
JWT_SECRET=
GROQ_API_KEY=
REDIS_URL=redis://redis:6379
FRONTEND_URL=http://localhost:3000

META_DB_HOST=postgres
META_DB_PORT=5432
META_DB_NAME=datahub_meta
META_DB_USER=datahub_user
META_DB_PASS=
```

- [ ] **Step 2: Criar backend/.gitignore**

```
.env
.env.dev
__pycache__/
*.pyc
*.pyo
.pytest_cache/
```

---

## Task 10: Frontend — Design System (app.css) + API + Stores

**Files:**
- Modify: `frontend/src/app.css`
- Create: `frontend/src/lib/api.js`
- Create: `frontend/src/lib/stores/company.js`
- Create: `frontend/.env.example`

**Interfaces:**
- Produces: variáveis CSS `--bg`, `--surface`, `--border`, `--text`, `--muted`, `--accent-*`; objeto `api` com todos os métodos; stores `empresa`, `usuario`, `token`

- [ ] **Step 1: Criar frontend/src/app.css**

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --bg:          #0d1117;
  --surface:     #161b22;
  --surface2:    #1c2128;
  --border:      #21262d;
  --text:        #e6edf3;
  --muted:       #7d8590;
  --accent:      #f78166;
  --accent-blue: #79c0ff;
  --accent-green:#56d364;
  --accent-purple:#d2a8ff;
  --accent-orange:#ffa657;
  --font-display:'IBM Plex Mono', monospace;
  --font-body:   'Inter', sans-serif;
  --radius:      6px;
  --radius-lg:   12px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.5;
  height: 100%;
}

a { color: var(--accent-blue); text-decoration: none; }
a:hover { text-decoration: underline; }

button {
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 14px;
  border: none;
  border-radius: var(--radius);
  padding: 8px 16px;
  transition: opacity .15s;
}
button:hover { opacity: .85; }
button:disabled { opacity: .4; cursor: not-allowed; }

.btn-primary {
  background: var(--accent);
  color: #0d1117;
  font-weight: 600;
}
.btn-ghost {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
}

input, select, textarea {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
  padding: 8px 12px;
  width: 100%;
  outline: none;
  transition: border-color .15s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--accent-blue);
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
}

.error { color: var(--accent); font-size: 13px; }

/* Grid de widgets do dashboard */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 24px;
}
.widget--full    { grid-column: 1 / -1; }
.widget--half    { grid-column: span 2; }
.widget--third   { grid-column: span 1; }
.widget--quarter { grid-column: span 1; }

@media (max-width: 900px) {
  .dashboard-grid { grid-template-columns: 1fr 1fr; }
  .widget--quarter { grid-column: span 1; }
}
@media (max-width: 600px) {
  .dashboard-grid { grid-template-columns: 1fr; }
  .widget--half, .widget--quarter, .widget--third { grid-column: 1 / -1; }
}
```

- [ ] **Step 2: Criar frontend/src/lib/stores/company.js**

```javascript
import { writable } from 'svelte/store';

export const empresa  = writable(null);
export const usuario  = writable(null);
export const token    = writable(
  typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null
);
```

- [ ] **Step 3: Criar frontend/src/lib/api.js**

```javascript
const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  const tok = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (email, senha, company_slug) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, senha, company_slug }) }),
  me: () => request('/api/auth/me'),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  // Charts (dinâmico por slug)
  chart: (slug, params = {}) => {
    const p = new URLSearchParams(params);
    return request(`/api/charts/${slug}?${p}`);
  },

  // Tables
  pedidos: (params = {}) => {
    const p = new URLSearchParams(params);
    return request(`/api/tables/pedidos?${p}`);
  },

  // IA
  perguntarIA:  (pergunta) =>
    request('/api/ai/ask', { method: 'POST', body: JSON.stringify({ pergunta }) }),
  historicoIA:  () => request('/api/ai/historico'),

  // Reports
  solicitarRelatorio: (tipo = 'relatorio_mensal') =>
    request('/api/reports/solicitar', { method: 'POST', body: JSON.stringify({ tipo }) }),
  statusRelatorio: (id) => request(`/api/reports/status/${id}`),
  resultadoRelatorio: (id) => request(`/api/reports/resultado/${id}`),

  // Queries (admin)
  listarQueries: (tipo, empresa_id) => {
    const p = new URLSearchParams();
    if (tipo) p.append('tipo', tipo);
    if (empresa_id) p.append('empresa_id', String(empresa_id));
    return request(`/api/queries/?${p}`);
  },
  buscarQuery:    (id)   => request(`/api/queries/${id}`),
  criarQuery:     (data) => request('/api/queries/', { method: 'POST', body: JSON.stringify(data) }),
  atualizarQuery: (id, data) =>
    request(`/api/queries/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletarQuery:   (id)   => request(`/api/queries/${id}`, { method: 'DELETE' }),
  testarQuery:    (data) =>
    request('/api/queries/testar', { method: 'POST', body: JSON.stringify(data) }),
  executarQuery:  (slug, params = {}) => {
    const p = new URLSearchParams(params);
    return request(`/api/queries/executar/${slug}?${p}`);
  },
  layoutDashboard: () => request('/api/queries/layout/dashboard'),
};
```

- [ ] **Step 4: Criar frontend/.env.example**

```env
VITE_API_URL=http://localhost:3001
```

---

## Task 11: Frontend — Componentes (KPICard, ChartPanel, MapPanel)

**Files:**
- Create: `frontend/src/lib/components/KPICard.svelte`
- Create: `frontend/src/lib/components/ChartPanel.svelte`
- Create: `frontend/src/lib/components/MapPanel.svelte`

**Interfaces:**
- KPICard: prop `dados: {valor, label, prefixo, delta?, delta_dir?}`
- ChartPanel: props `tipo: string`, `dados: array`
- MapPanel: prop `pontos: [{lat, lng, valor, label}]`

- [ ] **Step 1: Criar frontend/src/lib/components/KPICard.svelte**

```svelte
<script>
  export let dados = null;

  $: valor = dados?.valor ?? 0;
  $: label = dados?.label ?? '—';
  $: prefixo = dados?.prefixo ?? '';
  $: delta = dados?.delta ?? null;
  $: deltaDir = dados?.delta_dir ?? null;

  const fmt = (v) => {
    if (prefixo === 'R$') {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
    }
    if (prefixo === '%') return `${Number(v).toFixed(1)}%`;
    return new Intl.NumberFormat('pt-BR').format(v);
  };
</script>

<div class="kpi-card card">
  <span class="label">{label}</span>
  <span class="valor">{fmt(valor)}</span>
  {#if delta !== null}
    <span class="delta" class:up={deltaDir === 'up'} class:down={deltaDir === 'down'}>
      {deltaDir === 'up' ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%
    </span>
  {/if}
</div>

<style>
.kpi-card { display: flex; flex-direction: column; gap: 6px; }
.label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.valor { font-family: var(--font-display); font-size: 28px; font-weight: 500; color: var(--text); }
.delta { font-size: 12px; font-weight: 600; }
.delta.up   { color: var(--accent-green); }
.delta.down { color: var(--accent); }
</style>
```

- [ ] **Step 2: Instalar ECharts e Leaflet no frontend (se não instalado)**

```bash
cd frontend && npm install echarts leaflet
```
Esperado: instalação sem erros.

- [ ] **Step 3: Criar frontend/src/lib/components/ChartPanel.svelte**

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import * as echarts from 'echarts';

  export let tipo = 'bar';
  export let dados = [];

  let container;
  let chart;

  const COLORS = ['#79c0ff','#f78166','#56d364','#d2a8ff','#ffa657','#39d353'];

  function buildOption(tipo, dados) {
    const labels = dados.map(d => d.label);
    const values = dados.map(d => Number(d.valor));

    if (tipo === 'chart_doughnut') {
      return {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', right: 10, textStyle: { color: '#e6edf3' } },
        series: [{
          type: 'pie', radius: ['45%', '70%'],
          data: dados.map((d, i) => ({ value: Number(d.valor), name: d.label, itemStyle: { color: COLORS[i % COLORS.length] } })),
          label: { color: '#e6edf3' }
        }]
      };
    }

    const isHorizontal = tipo === 'chart_bar_horizontal';
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: isHorizontal
        ? { type: 'value', axisLabel: { color: '#7d8590' }, splitLine: { lineStyle: { color: '#21262d' } } }
        : { type: 'category', data: labels, axisLabel: { color: '#7d8590' } },
      yAxis: isHorizontal
        ? { type: 'category', data: labels, axisLabel: { color: '#7d8590' } }
        : { type: 'value', axisLabel: { color: '#7d8590' }, splitLine: { lineStyle: { color: '#21262d' } } },
      series: [{
        type: tipo === 'chart_line' ? 'line' : 'bar',
        data: values,
        smooth: tipo === 'chart_line',
        itemStyle: { color: '#79c0ff' },
        areaStyle: tipo === 'chart_line' ? { color: 'rgba(121,192,255,.1)' } : undefined,
        barMaxWidth: 40,
      }]
    };
  }

  onMount(() => {
    chart = echarts.init(container, null, { renderer: 'svg' });
    if (dados.length) chart.setOption(buildOption(tipo, dados));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(container);
    return () => ro.disconnect();
  });

  $: if (chart && dados.length) chart.setOption(buildOption(tipo, dados), true);

  onDestroy(() => chart?.dispose());
</script>

<div bind:this={container} style="width:100%;height:260px;"></div>
```

- [ ] **Step 4: Criar frontend/src/lib/components/MapPanel.svelte**

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';

  export let pontos = [];

  let container;
  let map;
  let markers = [];

  onMount(async () => {
    const L = (await import('leaflet')).default;
    await import('leaflet/dist/leaflet.css');

    map = L.map(container, { zoomControl: true, attributionControl: false }).setView([-15.8, -47.9], 4);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19
    }).addTo(map);

    renderPontos(L);
  });

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

  onDestroy(() => map?.remove());
</script>

<div bind:this={container} style="width:100%;height:300px;border-radius:8px;overflow:hidden;"></div>
```

---

## Task 12: Frontend — Componentes (DataTable, AIChat, QueryEditor)

**Files:**
- Create: `frontend/src/lib/components/DataTable.svelte`
- Create: `frontend/src/lib/components/AIChat.svelte`
- Create: `frontend/src/lib/components/QueryEditor.svelte`

- [ ] **Step 1: Criar frontend/src/lib/components/DataTable.svelte**

```svelte
<script>
  import { createEventDispatcher } from 'svelte';

  export let colunas = [];
  export let dados   = [];
  export let total   = 0;
  export let page    = 1;

  const dispatch = createEventDispatcher();
  $: pages = Math.ceil(total / (dados.length || 20)) || 1;

  const fmtValor = (v) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);

  const STATUS_COLOR = {
    concluido: 'var(--accent-green)',
    pendente:  'var(--accent-orange)',
    cancelado: 'var(--accent)',
  };
</script>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        {#each colunas as col}
          <th>{col.label ?? col.key}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each dados as row}
        <tr>
          {#each colunas as col}
            <td>
              {#if col.key === 'status'}
                <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
                {row[col.key]}
              {:else if col.key === 'valor'}
                {fmtValor(row[col.key])}
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>

  <div class="pagination">
    <span>{total} registros</span>
    <div class="btns">
      <button class="btn-ghost" on:click={() => dispatch('page', page - 1)} disabled={page <= 1}>← Anterior</button>
      <span>Pág {page} / {pages}</span>
      <button class="btn-ghost" on:click={() => dispatch('page', page + 1)} disabled={page >= pages}>Próxima →</button>
    </div>
  </div>
</div>

<style>
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
tr:hover td { background: var(--surface2); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.pagination { display: flex; justify-content: space-between; align-items: center; padding: 12px 0 0; color: var(--muted); font-size: 13px; }
.btns { display: flex; gap: 8px; align-items: center; }
</style>
```

- [ ] **Step 2: Criar frontend/src/lib/components/AIChat.svelte**

```svelte
<script>
  import { api } from '$lib/api.js';

  let input = '';
  let historico = [];
  let carregando = false;

  async function enviar() {
    if (!input.trim() || carregando) return;
    const pergunta = input.trim();
    input = '';
    historico = [...historico, { tipo: 'user', texto: pergunta }];
    carregando = true;
    try {
      const res = await api.perguntarIA(pergunta);
      historico = [...historico, { tipo: 'ai', texto: res.resposta }];
    } catch (e) {
      historico = [...historico, { tipo: 'error', texto: 'Erro ao obter resposta.' }];
    } finally {
      carregando = false;
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
  }
</script>

<div class="chat">
  <div class="messages">
    {#each historico as msg}
      <div class="msg msg--{msg.tipo}">
        <span class="origin">{msg.tipo === 'user' ? 'Você' : msg.tipo === 'ai' ? 'IA' : '!'}</span>
        <p>{msg.texto}</p>
      </div>
    {/each}
    {#if carregando}
      <div class="msg msg--ai loading">
        <span class="origin">IA</span>
        <p>Analisando dados<span class="dots">...</span></p>
      </div>
    {/if}
  </div>

  <div class="input-row">
    <textarea
      bind:value={input}
      on:keydown={onKeydown}
      placeholder="Pergunte sobre os dados da empresa..."
      rows="2"
      disabled={carregando}
    ></textarea>
    <button class="btn-primary" on:click={enviar} disabled={carregando || !input.trim()}>
      Enviar
    </button>
  </div>
</div>

<style>
.chat { display: flex; flex-direction: column; height: 100%; gap: 16px; }
.messages { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; max-height: 400px; padding-right: 4px; }
.msg { padding: 12px 16px; border-radius: var(--radius); max-width: 85%; }
.msg--user  { background: var(--surface2); align-self: flex-end; }
.msg--ai    { background: var(--surface); border: 1px solid var(--border); align-self: flex-start; }
.msg--error { background: rgba(247,129,102,.1); border: 1px solid var(--accent); align-self: flex-start; }
.origin { display: block; font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row textarea { resize: none; }
@keyframes blink { 50% { opacity: 0; } }
.dots { animation: blink 1s infinite; }
</style>
```

- [ ] **Step 3: Criar frontend/src/lib/components/QueryEditor.svelte**

```svelte
<script>
  export let sql   = '';
  export let tipo  = 'kpi';
  export let onTestar;

  let linhas     = 0;
  let colunas    = [];
  let amostra    = [];
  let erro       = null;
  let testando   = false;

  const contratos = {
    kpi:                  ['valor', 'label'],
    chart_line:           ['label', 'valor'],
    chart_bar:            ['label', 'valor'],
    chart_bar_horizontal: ['label', 'valor'],
    chart_doughnut:       ['label', 'valor'],
    table:                [],
    rag_context:          [],
  };

  $: colunasEsperadas  = contratos[tipo] || [];
  $: colunasFaltando   = colunasEsperadas.filter(c => !colunas.includes(c));
  $: contratoOk        = colunas.length > 0 && colunasFaltando.length === 0;

  async function testar() {
    testando = true;
    erro = null;
    const res = await onTestar(sql);
    if (res.ok) {
      linhas  = res.linhas;
      colunas = res.colunas;
      amostra = res.amostra;
    } else {
      erro = res.erro;
      linhas = 0; colunas = []; amostra = [];
    }
    testando = false;
  }
</script>

<div class="editor">
  <textarea
    bind:value={sql}
    rows="8"
    placeholder="SELECT coluna AS label, valor FROM tabela WHERE ..."
    style="font-family: var(--font-display); font-size: 13px;"
  ></textarea>

  <button class="btn-ghost" on:click={testar} disabled={testando || !sql.trim()}>
    {testando ? 'Testando...' : 'Testar Query'}
  </button>

  {#if erro}
    <p class="error">{erro}</p>
  {/if}

  {#if colunas.length > 0}
    <div class="result-info">
      <span>{linhas} linha(s) retornada(s)</span>
      <span>Colunas: {colunas.join(', ')}</span>
      {#if colunasFaltando.length > 0}
        <p class="error">⚠ Colunas obrigatórias faltando para tipo "{tipo}": {colunasFaltando.join(', ')}</p>
      {:else if colunasEsperadas.length > 0}
        <p style="color: var(--accent-green)">✓ Contrato OK</p>
      {/if}
    </div>

    {#if amostra.length > 0}
      <div class="preview">
        <table>
          <thead><tr>{#each colunas as c}<th>{c}</th>{/each}</tr></thead>
          <tbody>
            {#each amostra as row}
              <tr>{#each colunas as c}<td>{row[c] ?? '—'}</td>{/each}</tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</div>

<style>
.editor { display: flex; flex-direction: column; gap: 10px; }
.result-info { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--muted); }
.preview { overflow-x: auto; }
.preview table { border-collapse: collapse; font-size: 12px; }
.preview th, .preview td { padding: 6px 10px; border: 1px solid var(--border); }
.preview th { background: var(--surface2); color: var(--muted); }
</style>
```

---

## Task 13: Frontend — Rotas (+layout, +page, /login, /ai)

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`
- Modify: `frontend/src/routes/+page.svelte`
- Create: `frontend/src/routes/login/+page.svelte`
- Create: `frontend/src/routes/ai/+page.svelte`

- [ ] **Step 1: Substituir frontend/src/routes/+layout.svelte**

```svelte
<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { token, empresa, usuario } from '$lib/stores/company.js';
  import { api } from '$lib/api.js';
  import '../app.css';

  let sidebarOpen = true;

  const navLinks = [
    { href: '/',                     label: 'Dashboard'   },
    { href: '/ai',                   label: 'IA / Chat'   },
    { href: '/configuracoes/queries',label: 'Config'      },
  ];

  onMount(async () => {
    const tok = localStorage.getItem('token');
    if (!tok && $page.url.pathname !== '/login') {
      goto('/login');
      return;
    }
    if (tok && !$usuario) {
      try {
        const me = await api.me();
        usuario.set(me);
        empresa.set({ nome: me.company_name, slug: me.company_slug });
      } catch {
        localStorage.removeItem('token');
        token.set(null);
        goto('/login');
      }
    }
  });
</script>

{#if $page.url.pathname === '/login'}
  <slot />
{:else}
  <div class="shell">
    <nav class="sidebar" class:collapsed={!sidebarOpen}>
      <div class="sidebar-header">
        <span class="logo">DataHub</span>
        <button class="btn-ghost icon-btn" on:click={() => sidebarOpen = !sidebarOpen}>≡</button>
      </div>

      {#if $empresa}
        <div class="empresa-badge">{$empresa.nome}</div>
      {/if}

      <ul class="nav-links">
        {#each navLinks as link}
          <li class:active={$page.url.pathname === link.href}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}
      </ul>

      <button class="btn-ghost logout" on:click={async () => {
        await api.logout().catch(() => {});
        localStorage.removeItem('token');
        token.set(null);
        usuario.set(null);
        goto('/login');
      }}>Sair</button>
    </nav>

    <main class="content">
      <slot />
    </main>
  </div>
{/if}

<style>
.shell { display: flex; height: 100vh; overflow: hidden; }
.sidebar {
  width: 220px; min-width: 220px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  padding: 16px 0;
  transition: width .2s, min-width .2s;
}
.sidebar.collapsed { width: 56px; min-width: 56px; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px 16px; }
.logo { font-family: var(--font-display); font-size: 16px; color: var(--accent); font-weight: 500; }
.empresa-badge { margin: 0 12px 12px; padding: 6px 10px; background: var(--surface2); border-radius: var(--radius); font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-links { list-style: none; flex: 1; }
.nav-links li a { display: block; padding: 10px 20px; color: var(--muted); font-size: 14px; }
.nav-links li.active a { color: var(--text); background: var(--surface2); border-left: 2px solid var(--accent-blue); }
.nav-links li a:hover { color: var(--text); background: var(--surface2); text-decoration: none; }
.logout { margin: 8px 12px 0; width: calc(100% - 24px); }
.content { flex: 1; overflow-y: auto; }
.icon-btn { padding: 4px 8px; }
</style>
```

- [ ] **Step 2: Substituir frontend/src/routes/+page.svelte (dashboard dinâmico)**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import KPICard    from '$lib/components/KPICard.svelte';
  import ChartPanel from '$lib/components/ChartPanel.svelte';
  import DataTable  from '$lib/components/DataTable.svelte';

  let layout  = [];
  let dados   = {};
  let loading = true;
  let erro    = null;

  const COLUNAS_PEDIDOS = [
    { key: 'id',           label: 'ID' },
    { key: 'cliente_nome', label: 'Cliente' },
    { key: 'produto',      label: 'Produto' },
    { key: 'valor',        label: 'Valor' },
    { key: 'status',       label: 'Status' },
    { key: 'canal',        label: 'Canal' },
    { key: 'data',         label: 'Data' },
  ];

  onMount(async () => {
    try {
      layout = await api.layoutDashboard();

      const resultados = await Promise.allSettled(
        layout.map(w => api.executarQuery(w.query_slug))
      );

      resultados.forEach((res, i) => {
        const slug = layout[i].query_slug;
        dados[slug] = res.status === 'fulfilled' ? res.value : { erro: res.reason?.message };
      });
      dados = dados;
    } catch (e) {
      erro = e.message;
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head><title>Dashboard — DataHub</title></svelte:head>

{#if loading}
  <div class="dashboard-grid">
    {#each Array(8) as _}
      <div class="card skeleton widget--quarter" style="height:100px;"></div>
    {/each}
  </div>

{:else if erro}
  <div style="padding:24px;" class="error">Erro ao carregar dashboard: {erro}</div>

{:else}
  <div class="dashboard-grid">
    {#each layout as widget (widget.query_slug)}
      <div class="widget widget--{widget.largura} card">
        <h3 class="widget-title">{widget.titulo}</h3>

        {#if dados[widget.query_slug]?.erro}
          <p class="error" style="font-size:13px">Erro: {dados[widget.query_slug].erro}</p>

        {:else if widget.tipo === 'kpi'}
          <KPICard dados={dados[widget.query_slug]?.data?.[0]} />

        {:else if widget.tipo?.startsWith('chart_')}
          <ChartPanel tipo={widget.tipo} dados={dados[widget.query_slug]?.data ?? []} />

        {:else if widget.tipo === 'table'}
          <DataTable
            colunas={COLUNAS_PEDIDOS}
            dados={dados[widget.query_slug]?.data ?? []}
            total={dados[widget.query_slug]?.data?.length ?? 0}
            page={1}
          />
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
.widget-title { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 12px; }
@keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:.8} }
.skeleton { animation: pulse 1.5s infinite; }
</style>
```

- [ ] **Step 3: Criar frontend/src/routes/login/+page.svelte**

```svelte
<script>
  import { goto } from '$app/navigation';
  import { token, usuario } from '$lib/stores/company.js';
  import { api } from '$lib/api.js';

  let email        = '';
  let senha        = '';
  let company_slug = 'alpha';
  let erro         = '';
  let carregando   = false;

  const empresas = [
    { slug: 'alpha', nome: 'Empresa Alpha Ltda' },
    { slug: 'beta',  nome: 'Beta Comércio S.A.' },
    { slug: 'gamma', nome: 'Gamma Tech ME' },
  ];

  async function login() {
    erro = '';
    carregando = true;
    try {
      const res = await api.login(email, senha, company_slug);
      localStorage.setItem('token', res.token);
      token.set(res.token);
      goto('/');
    } catch (e) {
      erro = 'Email, senha ou empresa inválidos.';
    } finally {
      carregando = false;
    }
  }

  function onKeydown(e) {
    if (e.key === 'Enter') login();
  }
</script>

<svelte:head><title>Login — DataHub</title></svelte:head>

<div class="login-wrap">
  <div class="login-box card">
    <h1>DataHub</h1>
    <p class="subtitle">Analytics Multiempresa</p>

    <label>Email
      <input type="email" bind:value={email} on:keydown={onKeydown} placeholder="admin@datahub.local" />
    </label>

    <label>Senha
      <input type="password" bind:value={senha} on:keydown={onKeydown} placeholder="••••••••" />
    </label>

    <label>Empresa
      <select bind:value={company_slug}>
        {#each empresas as e}
          <option value={e.slug}>{e.nome}</option>
        {/each}
      </select>
    </label>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={login} disabled={carregando}>
      {carregando ? 'Entrando...' : 'Entrar'}
    </button>
  </div>
</div>

<style>
.login-wrap {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: var(--bg);
}
.login-box { width: 100%; max-width: 380px; display: flex; flex-direction: column; gap: 16px; }
h1 { font-family: var(--font-display); font-size: 28px; color: var(--accent); }
.subtitle { color: var(--muted); margin-top: -10px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
button { margin-top: 8px; }
</style>
```

- [ ] **Step 4: Criar frontend/src/routes/ai/+page.svelte**

```svelte
<script>
  import { onMount } from 'svelte';
  import AIChat from '$lib/components/AIChat.svelte';
  import { api } from '$lib/api.js';

  let historico = [];

  onMount(async () => {
    try {
      historico = await api.historicoIA();
    } catch {}
  });
</script>

<svelte:head><title>IA / Chat — DataHub</title></svelte:head>

<div style="padding:24px; max-width:800px; margin:0 auto;">
  <h2 style="margin-bottom:20px; font-family:var(--font-display); color:var(--accent-blue)">Assistente de Analytics</h2>

  {#if historico.length > 0}
    <details class="card" style="margin-bottom:16px;">
      <summary style="cursor:pointer; color:var(--muted); font-size:13px">
        Histórico de conversas ({historico.length})
      </summary>
      <div style="margin-top:12px; display:flex; flex-direction:column; gap:10px;">
        {#each historico as item}
          <div style="border-left:2px solid var(--border); padding-left:12px;">
            <p style="font-size:12px; color:var(--muted)">{item.criado_em}</p>
            <p style="font-weight:500">↑ {item.pergunta}</p>
            <p style="color:var(--muted); font-size:13px">↓ {item.resposta}</p>
          </div>
        {/each}
      </div>
    </details>
  {/if}

  <div class="card">
    <AIChat />
  </div>
</div>
```

---

## Task 14: Frontend — Configurações de Queries

**Files:**
- Create: `frontend/src/routes/configuracoes/queries/+page.svelte`
- Create: `frontend/src/routes/configuracoes/queries/nova/+page.svelte`

- [ ] **Step 1: Criar frontend/src/routes/configuracoes/queries/+page.svelte**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let queries     = [];
  let filtroTipo  = '';
  let loading     = true;
  let erro        = null;

  const tipos = [
    { value: '',                     label: 'Todos' },
    { value: 'kpi',                  label: 'KPI' },
    { value: 'chart_line',           label: 'Gráfico Linha' },
    { value: 'chart_bar',            label: 'Gráfico Barra' },
    { value: 'chart_bar_horizontal', label: 'Barra Horizontal' },
    { value: 'chart_doughnut',       label: 'Rosca' },
    { value: 'table',                label: 'Tabela' },
    { value: 'rag_context',          label: 'Contexto IA' },
  ];

  onMount(async () => {
    try {
      queries = await api.listarQueries();
    } catch (e) {
      erro = e.message;
    } finally {
      loading = false;
    }
  });

  $: filtradas = filtroTipo ? queries.filter(q => q.tipo === filtroTipo) : queries;

  async function toggleAtivo(q) {
    await api.atualizarQuery(q.id, { ativo: !q.ativo });
    q.ativo = !q.ativo;
    queries = queries;
  }

  async function deletar(q) {
    if (!confirm(`Deletar "${q.nome}"?`)) return;
    try {
      await api.deletarQuery(q.id);
      queries = queries.filter(x => x.id !== q.id);
    } catch (e) {
      alert('Erro ao deletar: ' + e.message);
    }
  }
</script>

<svelte:head><title>Queries — DataHub</title></svelte:head>

<div style="padding:24px;">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
    <h2 style="font-family:var(--font-display)">Queries do Dashboard</h2>
    <a href="/configuracoes/queries/nova" class="btn-primary" style="display:inline-block; padding:8px 16px; border-radius:6px; color:#0d1117; background:var(--accent); font-weight:600; text-decoration:none">Nova Query</a>
  </div>

  <div style="margin-bottom:16px;">
    <select bind:value={filtroTipo} style="width:200px;">
      {#each tipos as t}<option value={t.value}>{t.label}</option>{/each}
    </select>
  </div>

  {#if loading}
    <p style="color:var(--muted)">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <div class="card" style="padding:0; overflow:hidden;">
      <table style="width:100%; border-collapse:collapse;">
        <thead>
          <tr>
            {#each ['Slug', 'Nome', 'Tipo', 'Cache TTL', 'Escopo', 'Ativo', 'Ações'] as h}
              <th style="padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); font-size:11px; text-transform:uppercase; color:var(--muted);">{h}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each filtradas as q}
            <tr>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); font-family:var(--font-display); font-size:12px;">{q.slug}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border);">{q.nome}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--accent-blue); font-size:12px;">{q.tipo}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--muted);">{q.cache_ttl}s</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border); color:var(--muted);">{q.empresa_id ? `Empresa #${q.empresa_id}` : 'Global'}</td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border);">
                <button class="btn-ghost" style="padding:4px 10px; font-size:12px;" on:click={() => toggleAtivo(q)}>
                  {q.ativo ? '✓ Ativo' : '✗ Inativo'}
                </button>
              </td>
              <td style="padding:10px 14px; border-bottom:1px solid var(--border);">
                <button class="btn-ghost" style="padding:4px 10px; font-size:12px; color:var(--accent);" on:click={() => deletar(q)}>Deletar</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
```

- [ ] **Step 2: Criar frontend/src/routes/configuracoes/queries/nova/+page.svelte**

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

  let testando      = false;
  let resultadoTeste = null;
  let salvando      = false;
  let erro          = null;

  const tipos = [
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context'
  ];

  async function testar(sql) {
    return api.testarQuery({ ...form, sql_texto: sql });
  }

  async function salvar() {
    if (!resultadoTeste?.ok) {
      erro = 'Teste a query antes de salvar.';
      return;
    }
    erro = null;
    salvando = true;
    try {
      await api.criarQuery(form);
      goto('/configuracoes/queries');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Query — DataHub</title></svelte:head>

<div style="padding:24px; max-width:800px; margin:0 auto;">
  <div style="display:flex; align-items:center; gap:16px; margin-bottom:24px;">
    <a href="/configuracoes/queries" style="color:var(--muted)">← Voltar</a>
    <h2 style="font-family:var(--font-display)">Nova Query</h2>
  </div>

  <div class="card" style="display:flex; flex-direction:column; gap:16px;">
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
      <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
        Slug (identificador único)
        <input bind:value={form.slug} placeholder="ex: kpi_receita" />
      </label>
      <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
        Nome legível
        <input bind:value={form.nome} placeholder="ex: Receita Total (30d)" />
      </label>
    </div>

    <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
      Tipo
      <select bind:value={form.tipo}>
        {#each tipos as t}<option value={t}>{t}</option>{/each}
      </select>
    </label>

    <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)">
      Cache TTL (segundos, 0 = sem cache)
      <input type="number" bind:value={form.cache_ttl} min="0" />
    </label>

    <div style="border-top:1px solid var(--border); padding-top:16px;">
      <p style="font-size:13px; color:var(--muted); margin-bottom:10px;">SQL da Query</p>
      <QueryEditor
        bind:sql={form.sql_texto}
        tipo={form.tipo}
        onTestar={testar}
      />
    </div>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={salvar} disabled={salvando}>
      {salvando ? 'Salvando...' : 'Salvar Query'}
    </button>
  </div>
</div>
```

---

## Task 15: Frontend — Dockerfile + nginx + Root files

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `.gitignore` (raiz)
- Create: `README.md`

- [ ] **Step 1: Criar frontend/Dockerfile**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 2: Criar frontend/nginx.conf**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

- [ ] **Step 3: Criar .gitignore raiz**

```
# Env
**/.env
**/.env.dev
!**/.env.example

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Node
node_modules/
frontend/build/
frontend/.svelte-kit/

# Docker
*.log
```

- [ ] **Step 4: Criar README.md**

```markdown
# DataHub — Analytics Multiempresa

Sistema de analytics configurável para múltiplas empresas. Cada empresa tem seu próprio banco PostgreSQL; um banco central controla usuários, permissões e histórico de chat. O dashboard é totalmente dinâmico: os widgets são definidos por queries SQL cadastradas no painel de configurações.

Desenvolvido com FastAPI + asyncpg + Redis + SvelteKit + ECharts + Groq LLaMA 3.3 70B.

## Pré-requisitos

- Docker + Docker Compose
- Node.js 20+ (apenas para dev local sem Docker)
- Conta gratuita no [Groq Console](https://console.groq.com) para obter `GROQ_API_KEY`

## Rodando localmente

```bash
# 1. Clone e configure variáveis
cp backend/.env.example backend/.env.dev
# Edite backend/.env.dev com sua GROQ_API_KEY e um JWT_SECRET de 32+ chars

# 2. Suba o stack completo
docker compose -f docker-compose.dev.yml up --build

# 3. Acesse
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:3001/docs
# Login:     admin@datahub.local / admin123 / empresa: alpha
```

## Variáveis de ambiente (backend)

| Variável          | Descrição                              |
|-------------------|----------------------------------------|
| `JWT_SECRET`      | String aleatória 32+ caracteres        |
| `GROQ_API_KEY`    | Chave da API Groq (console.groq.com)   |
| `REDIS_URL`       | URL do Redis (redis://redis:6379)      |
| `META_DB_HOST`    | Host do PostgreSQL (postgres em Docker)|
| `META_DB_NAME`    | datahub_meta                           |
| `META_DB_USER`    | datahub_user                           |
| `META_DB_PASS`    | Senha do usuário datahub_user          |
| `FRONTEND_URL`    | URL do frontend (para CORS)            |

## Adicionar nova empresa

```sql
-- No banco datahub_meta
INSERT INTO empresas (slug, nome, db_host, db_name, db_user, db_pass)
VALUES ('nova', 'Empresa Nova', 'postgres', 'nova_db', 'nova_user', 'senha');

INSERT INTO usuario_empresas (usuario_id, empresa_id)
VALUES (1, (SELECT id FROM empresas WHERE slug = 'nova'));
```
Não é necessário reiniciar o backend — o pool é criado sob demanda.

## Deploy no EasyPanel

1. Criar projeto `datahub` no EasyPanel
2. Adicionar serviços: `redis` (imagem Redis), `backend` e `worker` (Dockerfile do /backend), `frontend` (Dockerfile do /frontend)
3. No serviço `worker`, sobrescrever comando: `python -m arq worker.WorkerSettings`
4. Configurar variáveis de ambiente no EasyPanel (não usar .env em produção)
5. Liberar acesso Docker no pg_hba.conf do PostgreSQL do VPS (range 172.17.0.0/16)
```

- [ ] **Step 5: Testar stack completo**

```bash
docker compose -f docker-compose.dev.yml up --build
```

Verificar:
- `http://localhost:3001/docs` → Swagger com todas as rotas
- `http://localhost:3001/api/health` → `{"ok":true,"version":"1.0.0"}`
- `http://localhost:3000` → Tela de login (ou redirect para /login)
- Login com `admin@datahub.local` / `admin123` / empresa `alpha` → redireciona para dashboard
- Dashboard carrega widgets dinamicamente
- `/ai` → chatbot responde

---

## Self-Review

**Cobertura do spec:**
- ✅ Fase 1: Estrutura de pastas (já existia)
- ✅ Fase 2: SQL (scripts/init-db.sql já completo — [PERGUNTAR 1] respondido: alpha/beta/gamma)
- ✅ Fase 3: Arquivos de config backend
- ✅ Fase 4: Services (cache, groq, rag dinâmico) — [PERGUNTAR 2] respondido: tabela `pedidos` com colunas reais do init-db.sql
- ✅ Fase 5: Middleware auth com require_admin
- ✅ Fase 6: Rotas auth, charts, tables, ai, reports — [PERGUNTAR 3] respondido: chart_pedidos_status + chart_canal_vendas nos seeds
- ✅ Fase 6.5: Queries dinâmicas (routes/queries.py + query_runner.py) — [PERGUNTAR 4] respondido: colunas da tabela pedidos nos seeds
- ✅ Fase 7: Dockerfile backend (já existia Dockerfile.dev)
- ✅ Fase 8: Frontend SvelteKit (já inicializado) + componentes + rotas
- ✅ Fase 9: Dockerfile frontend + nginx.conf
- ✅ Fase 10: docker-compose.dev.yml (já existia completo)
- ✅ Fase 11: .gitignore raiz
- ✅ Fase 12: README.md

**Checklist de segurança:**
- `validar_sql()` bloqueia DROP/TRUNCATE/DELETE/INSERT/UPDATE
- `.env.dev` no .gitignore
- Senhas das empresas no banco, não em env vars
- `require_admin` protege endpoints de CRUD de queries
- JWT blacklist via Redis no logout

**Inconsistências corrigidas:**
- `build_context(company_slug, empresa_id)` — 2 argumentos na versão dinâmica (routes/ai.py passa ambos)
- `require_admin` definido em middleware/auth.py (faltava no spec original)
- `from_cache: True` retorna `tipo` no dict (consistência com `from_cache: False`)
- `docker-compose.dev.yml` usa hostname `postgres`, não `172.17.0.1` (correto para Docker)
