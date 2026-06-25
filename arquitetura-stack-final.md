# DataHub — Arquitetura Completa (Stack Final)
## SvelteKit + FastAPI + PostgreSQL Multi-banco + Redis + Groq + EasyPanel

---

## 1. ARQUITETURA GERAL

```
VPS (Ubuntu 22.04) — EasyPanel
│
├── Projeto: datahub
│   ├── frontend   → app.dominio.com.br       (SvelteKit)
│   ├── backend    → api.dominio.com.br       (FastAPI + asyncpg)
│   ├── worker     → interno                  (ARQ — tarefas assíncronas)
│   └── redis      → interno                  (cache + fila)
│
└── PostgreSQL (já no VPS, fora do Docker)
    ├── datahub_meta   ← NOVO: usuários, empresas, permissões, histórico chat
    ├── alpha_db
    ├── beta_db
    └── gamma_db

Fluxo de dados:
SvelteKit → FastAPI → Redis (cache hit?)
                    ↓ cache miss
                    asyncpg → PostgreSQL (empresa correta)
                    ↓
                    Redis (armazena resultado)
                    ↓
                    SvelteKit

Fluxo do chatbot (RAG simplificado):
Pergunta do usuário
    ↓
FastAPI busca dados relevantes no banco da empresa
    ↓
Injeta dados no prompt → Groq (LLaMA 3)
    ↓
Resposta fundamentada nos dados reais
    ↓
Salva histórico no datahub_meta
```

---

## 2. STACK FINAL

| Camada           | Tecnologia                        |
|-----------------|-----------------------------------|
| Frontend        | SvelteKit + Vite                  |
| Gráficos        | Apache ECharts                    |
| Mapas           | Leaflet + OpenStreetMap           |
| Backend         | Python 3.12 + FastAPI             |
| DB async        | asyncpg                           |
| Cache           | Redis + redis-py (async)          |
| Fila/Worker     | ARQ (async task queue)            |
| IA / Chatbot    | Groq SDK (LLaMA 3.3 70B)         |
| Auth            | python-jose (JWT)                 |
| Meta-banco      | PostgreSQL — datahub_meta         |
| Deploy          | EasyPanel (Docker)                |
| Proxy/HTTPS     | Traefik (embutido EasyPanel)      |

---

## 3. ESTRUTURA DE PASTAS

```
datahub/                          ← repositório Git
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                   ← FastAPI app
│   ├── worker.py                 ← ARQ worker (relatórios assíncronos)
│   ├── config/
│   │   ├── settings.py           ← variáveis de ambiente
│   │   ├── databases.py          ← pools asyncpg por empresa
│   │   └── redis.py              ← cliente Redis
│   ├── routes/
│   │   ├── auth.py               ← login/logout/JWT
│   │   ├── charts.py             ← KPIs, gráficos
│   │   ├── tables.py             ← tabelas dinâmicas
│   │   ├── ai.py                 ← chatbot com RAG
│   │   └── reports.py            ← dispara tarefas assíncronas
│   ├── middleware/
│   │   └── auth.py               ← validação JWT + company_id
│   └── services/
│       ├── cache.py              ← helpers de cache Redis
│       ├── rag.py                ← busca dados + monta prompt
│       └── groq_client.py        ← integração Groq
│
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    └── src/
        ├── app.html
        ├── routes/
        │   ├── +layout.svelte    ← sidebar + topbar
        │   ├── +page.svelte      ← dashboard principal
        │   ├── charts/
        │   └── ai/
        ├── lib/
        │   ├── components/
        │   │   ├── KPICards.svelte
        │   │   ├── ChartPanel.svelte
        │   │   ├── MapPanel.svelte
        │   │   ├── DataTable.svelte
        │   │   └── AIChat.svelte
        │   ├── stores/
        │   │   └── company.js    ← store global da empresa ativa
        │   └── api.js            ← chamadas ao backend
        └── app.css
```

---

## 4. BANCO DATAHUB_META — ESTRUTURA SQL

```sql
-- Executar no PostgreSQL do VPS
CREATE DATABASE datahub_meta;
CREATE USER datahub_user WITH PASSWORD 'senha_segura_aqui';
GRANT ALL PRIVILEGES ON DATABASE datahub_meta TO datahub_user;

\c datahub_meta

-- Empresas cadastradas
CREATE TABLE empresas (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(50) UNIQUE NOT NULL,  -- 'alpha', 'beta', 'gamma'
    nome        VARCHAR(100) NOT NULL,
    db_host     VARCHAR(100) NOT NULL,
    db_port     INTEGER DEFAULT 5432,
    db_name     VARCHAR(100) NOT NULL,
    db_user     VARCHAR(100) NOT NULL,
    db_pass     VARCHAR(100) NOT NULL,
    ativo       BOOLEAN DEFAULT true,
    criado_em   TIMESTAMP DEFAULT NOW()
);

-- Usuários do sistema
CREATE TABLE usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    senha_hash  VARCHAR(255) NOT NULL,
    role        VARCHAR(20) DEFAULT 'viewer',  -- 'admin', 'viewer'
    ativo       BOOLEAN DEFAULT true,
    criado_em   TIMESTAMP DEFAULT NOW()
);

-- Quais empresas cada usuário pode acessar
CREATE TABLE usuario_empresas (
    usuario_id  INTEGER REFERENCES usuarios(id),
    empresa_id  INTEGER REFERENCES empresas(id),
    PRIMARY KEY (usuario_id, empresa_id)
);

-- Histórico do chatbot por empresa e usuário
CREATE TABLE chat_historico (
    id          SERIAL PRIMARY KEY,
    usuario_id  INTEGER REFERENCES usuarios(id),
    empresa_id  INTEGER REFERENCES empresas(id),
    pergunta    TEXT NOT NULL,
    resposta    TEXT NOT NULL,
    criado_em   TIMESTAMP DEFAULT NOW()
);

-- Tarefas assíncronas (relatórios)
CREATE TABLE tarefas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo        VARCHAR(50) NOT NULL,  -- 'relatorio_mensal', 'exportar_csv'
    empresa_id  INTEGER REFERENCES empresas(id),
    usuario_id  INTEGER REFERENCES usuarios(id),
    status      VARCHAR(20) DEFAULT 'pendente',  -- 'pendente','rodando','ok','erro'
    payload     JSONB,
    resultado   JSONB,
    criado_em   TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);

-- Inserir empresas (ajuste as senhas)
INSERT INTO empresas (slug, nome, db_host, db_name, db_user, db_pass) VALUES
  ('alpha', 'Empresa Alpha', '172.17.0.1', 'alpha_db', 'alpha_user', 'senha_alpha'),
  ('beta',  'Empresa Beta',  '172.17.0.1', 'beta_db',  'beta_user',  'senha_beta'),
  ('gamma', 'Empresa Gamma', '172.17.0.1', 'gamma_db', 'gamma_user', 'senha_gamma');
```

---

## 5. BACKEND — CÓDIGO

### backend/requirements.txt
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
asyncpg==0.29.0
redis[asyncio]==5.0.4
arq==0.25.0
python-jose[cryptography]==3.3.0
bcrypt==4.1.2
groq==0.9.0
python-dotenv==1.0.1
httpx==0.27.0
pydantic-settings==2.2.1
```

### backend/Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
```

### backend/config/settings.py
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    PORT: int = 3001
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 480  # 8 horas

    # Meta banco (datahub_meta)
    META_DB_HOST: str = "172.17.0.1"
    META_DB_PORT: int = 5432
    META_DB_NAME: str = "datahub_meta"
    META_DB_USER: str = "datahub_user"
    META_DB_PASS: str

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # IA
    GROQ_API_KEY: str

    # Frontend
    FRONTEND_URL: str = "*"

    class Config:
        env_file = ".env"

settings = Settings()
```

### backend/config/databases.py
```python
import asyncpg
from typing import Dict, Optional
from config.settings import settings

# Pool do meta-banco (sempre ativo)
_meta_pool: Optional[asyncpg.Pool] = None

# Pools das empresas (criados sob demanda)
_company_pools: Dict[str, asyncpg.Pool] = {}


async def get_meta_pool() -> asyncpg.Pool:
    """Retorna o pool do banco datahub_meta."""
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
    """Busca config da empresa no meta-banco e cria pool sob demanda."""
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
    """Executa query no banco da empresa correta."""
    pool = await get_company_pool(company_slug)
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def query_meta(sql: str, *args):
    """Executa query no meta-banco."""
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)
```

### backend/config/redis.py
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

### backend/services/cache.py
```python
import json
from config.redis import get_redis

# TTLs em segundos
TTL_KPIS     = 300    # 5 minutos
TTL_CHARTS   = 600    # 10 minutos
TTL_MONTHLY  = 3600   # 1 hora


async def cache_get(key: str):
    redis = await get_redis()
    val = await redis.get(key)
    return json.loads(val) if val else None


async def cache_set(key: str, data, ttl: int = TTL_KPIS):
    redis = await get_redis()
    await redis.setex(key, ttl, json.dumps(data, default=str))


async def cache_del_prefix(prefix: str):
    """Invalida todo o cache de uma empresa (ex: ao atualizar dados)."""
    redis = await get_redis()
    keys = await redis.keys(f"{prefix}*")
    if keys:
        await redis.delete(*keys)
```

### backend/services/rag.py
```python
"""
RAG simplificado: busca dados reais do banco e injeta no prompt do chatbot.
Sem embeddings — funciona com queries SQL direcionadas pela pergunta.
"""
from config.databases import query_company


# Queries de contexto executadas antes de cada pergunta
CONTEXT_QUERIES = {
    "kpis": """
        SELECT
            COALESCE(SUM(valor), 0)        AS receita_total,
            COUNT(*)                        AS total_pedidos,
            AVG(valor)                      AS ticket_medio,
            COUNT(DISTINCT cliente_id)      AS clientes_ativos
        FROM pedidos
        WHERE data >= NOW() - INTERVAL '30 days'
    """,
    "top_produtos": """
        SELECT produto, COUNT(*) AS qtd, SUM(valor) AS total
        FROM pedidos
        WHERE data >= NOW() - INTERVAL '30 days'
        GROUP BY produto
        ORDER BY qtd DESC
        LIMIT 5
    """,
    "por_mes": """
        SELECT TO_CHAR(data, 'Mon/YY') AS mes, SUM(valor) AS total
        FROM pedidos
        WHERE data >= NOW() - INTERVAL '6 months'
        GROUP BY 1 ORDER BY MIN(data)
    """
}


async def build_context(company_slug: str) -> str:
    """Busca dados reais e retorna como texto para o prompt."""
    ctx_parts = []

    for name, sql in CONTEXT_QUERIES.items():
        try:
            rows = await query_company(company_slug, sql)
            rows_dict = [dict(r) for r in rows]
            ctx_parts.append(f"[{name}]: {rows_dict}")
        except Exception as e:
            ctx_parts.append(f"[{name}]: erro ao buscar ({e})")

    return "\n".join(ctx_parts)
```

### backend/services/groq_client.py
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

### backend/routes/ai.py
```python
from fastapi import APIRouter, Depends
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
    company_slug = user["company_slug"]
    company_name = user["company_name"]

    # Cache do contexto (evita queries repetidas a cada mensagem)
    ctx_key = f"rag_context:{company_slug}"
    context = await cache_get(ctx_key)
    if not context:
        context = await build_context(company_slug)
        await cache_set(ctx_key, context, ttl=TTL_CHARTS)
    elif isinstance(context, str) is False:
        context = json.dumps(context)

    # Chama o Groq com contexto real
    resposta = await ask(body.pergunta, context, company_name)

    # Salva histórico no meta-banco
    await query_meta(
        """INSERT INTO chat_historico (usuario_id, empresa_id, pergunta, resposta)
           VALUES ($1, $2, $3, $4)""",
        user["id"], user["empresa_id"], body.pergunta, resposta
    )

    return {"resposta": resposta}


@router.get("/historico")
async def historico(limit: int = 20, user=Depends(get_current_user)):
    rows = await query_meta(
        """SELECT pergunta, resposta, criado_em
           FROM chat_historico
           WHERE usuario_id = $1 AND empresa_id = $2
           ORDER BY criado_em DESC LIMIT $3""",
        user["id"], user["empresa_id"], limit
    )
    return [dict(r) for r in rows]
```

### backend/routes/charts.py
```python
from fastapi import APIRouter, Depends
from middleware.auth import get_current_user
from services.cache import cache_get, cache_set, TTL_KPIS, TTL_MONTHLY
from config.databases import query_company

router = APIRouter(prefix="/api/charts", tags=["Charts"])


@router.get("/kpis")
async def kpis(user=Depends(get_current_user)):
    slug = user["company_slug"]
    key  = f"kpis:{slug}"

    cached = await cache_get(key)
    if cached:
        return cached

    rows = await query_company(slug, """
        SELECT
            COALESCE(SUM(valor), 0)         AS receita,
            COUNT(*)                          AS pedidos,
            COALESCE(AVG(valor), 0)           AS ticket_medio,
            COUNT(DISTINCT cliente_id)        AS clientes
        FROM pedidos
        WHERE data >= NOW() - INTERVAL '30 days'
    """)

    result = dict(rows[0]) if rows else {}
    await cache_set(key, result, TTL_KPIS)
    return result


@router.get("/receita-mensal")
async def receita_mensal(user=Depends(get_current_user)):
    slug = user["company_slug"]
    key  = f"receita_mensal:{slug}"

    cached = await cache_get(key)
    if cached:
        return cached

    rows = await query_company(slug, """
        SELECT
            TO_CHAR(data, 'Mon') AS mes,
            EXTRACT(MONTH FROM data)::int AS mes_num,
            COALESCE(SUM(valor), 0) AS total
        FROM pedidos
        WHERE data >= NOW() - INTERVAL '12 months'
        GROUP BY 1, 2
        ORDER BY 2
    """)

    result = [dict(r) for r in rows]
    await cache_set(key, result, TTL_MONTHLY)
    return result
```

### backend/middleware/auth.py
```python
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from config.settings import settings
from config.databases import query_meta

security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Valida usuário e empresa no meta-banco
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
```

### backend/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from routes import auth, charts, tables, ai, reports

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


@app.get("/api/health")
async def health():
    return {"ok": True}
```

### backend/worker.py
```python
"""
ARQ Worker — processa tarefas pesadas em background (relatórios, exportações).
Roda como serviço separado no EasyPanel.
"""
from arq import cron
from config.databases import query_company, query_meta
from config.settings import settings
import json


async def gerar_relatorio_mensal(ctx, empresa_id: int, company_slug: str, usuario_id: int):
    """Tarefa: gera relatório mensal e salva resultado."""
    try:
        # Atualiza status
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
            """UPDATE tarefas SET status='ok', resultado=$1, concluido_em=NOW()
               WHERE empresa_id=$2 AND usuario_id=$3 AND status='rodando'""",
            json.dumps(resultado, default=str), empresa_id, usuario_id
        )

        return resultado

    except Exception as e:
        await query_meta(
            "UPDATE tarefas SET status='erro', resultado=$1 WHERE empresa_id=$2 AND usuario_id=$3",
            json.dumps({"erro": str(e)}), empresa_id, usuario_id
        )
        raise


class WorkerSettings:
    functions = [gerar_relatorio_mensal]
    redis_settings = {"host": "redis", "port": 6379}
    max_jobs = 10
```

---

## 6. FRONTEND — SVELTEKIT (ESTRUTURA BASE)

### frontend/Dockerfile
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

### frontend/nginx.conf
```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://backend:3001;
    }
}
```

### frontend/src/lib/api.js
```javascript
const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
    const token = localStorage.getItem('token');
    const res = await fetch(`${BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
        },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

export const api = {
    // Auth
    login: (email, senha, company_slug) =>
        request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, senha, company_slug })
        }),

    // Charts
    kpis:          () => request('/api/charts/kpis'),
    receitaMensal: () => request('/api/charts/receita-mensal'),

    // IA
    perguntarIA:   (pergunta) =>
        request('/api/ai/ask', {
            method: 'POST',
            body: JSON.stringify({ pergunta })
        }),
    historicoIA:   () => request('/api/ai/historico'),
};
```

### frontend/src/lib/stores/company.js
```javascript
import { writable } from 'svelte/store';

export const empresa = writable(null);   // { nome, slug }
export const usuario = writable(null);   // { nome, role }
export const token   = writable(
    typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null
);
```

---

## 7. DEPLOY NO EASYPANEL

### 7.1 Serviços a criar no projeto `datahub`

| Serviço   | Tipo        | Porta | Domínio                      |
|-----------|-------------|-------|------------------------------|
| redis     | Redis       | 6379  | interno                      |
| backend   | App (Docker)| 3001  | api.seu-dominio.com.br       |
| worker    | App (Docker)| —     | interno (sem domínio)        |
| frontend  | App (Docker)| 80    | app.seu-dominio.com.br       |

### 7.2 Variáveis de ambiente — backend e worker

```env
JWT_SECRET=gere_uma_chave_com_32_chars_aqui
GROQ_API_KEY=gsk_...
REDIS_URL=redis://redis:6379
FRONTEND_URL=https://app.seu-dominio.com.br

META_DB_HOST=172.17.0.1
META_DB_NAME=datahub_meta
META_DB_USER=datahub_user
META_DB_PASS=senha_do_meta
```

> As senhas das empresas ficam no banco `datahub_meta` (tabela `empresas`),
> não mais em variáveis de ambiente — muito mais fácil de gerenciar.

### 7.3 Comando do worker (diferente do backend)

No serviço `worker`, sobrescreva o comando padrão para:
```
python -m arq worker.WorkerSettings
```

### 7.4 Ordem de deploy
```
1. redis     → sobe primeiro
2. backend   → depende do redis e do postgres
3. worker    → depende do redis e do postgres
4. frontend  → último (aponta para o backend)
```

---

## 8. POSTGRESQL — LIBERAR ACESSO DOS CONTAINERS

```bash
# pg_hba.conf — adicionar ao final
host  datahub_meta  datahub_user  172.17.0.0/16  md5
host  alpha_db      alpha_user    172.17.0.0/16  md5
host  beta_db       beta_user     172.17.0.0/16  md5
host  gamma_db      gamma_user    172.17.0.0/16  md5

# postgresql.conf
listen_addresses = 'localhost,172.17.0.1'

# Reiniciar
systemctl restart postgresql
```

---

## 9. ADICIONAR NOVA EMPRESA

```sql
-- 1. Criar banco e usuário no Postgres
CREATE DATABASE nova_db;
CREATE USER nova_user WITH PASSWORD 'senha';
GRANT ALL PRIVILEGES ON DATABASE nova_db TO nova_user;

-- 2. Registrar no meta-banco (sem tocar em código ou .env)
INSERT INTO empresas (slug, nome, db_host, db_name, db_user, db_pass)
VALUES ('nova', 'Empresa Nova', '172.17.0.1', 'nova_db', 'nova_user', 'senha');

-- 3. Dar acesso ao usuário
INSERT INTO usuario_empresas (usuario_id, empresa_id)
VALUES (1, (SELECT id FROM empresas WHERE slug = 'nova'));
```

Não precisa reiniciar nenhum serviço — o pool é criado sob demanda.

---

## 10. CHECKLIST DE SEGURANÇA

- [ ] `.env` no `.gitignore` — variáveis apenas no EasyPanel
- [ ] Senhas das empresas no banco `datahub_meta`, não em env vars
- [ ] JWT_SECRET com 32+ caracteres aleatórios
- [ ] GROQ_API_KEY somente no backend/worker
- [ ] pg_hba.conf restrito ao range Docker `172.17.0.0/16`
- [ ] Porta 5432 bloqueada para internet (UFW)
- [ ] Redis sem senha só se for interno (sem porta exposta)
- [ ] HTTPS ativo em todos os domínios (automático EasyPanel)

```bash
ufw deny 5432
ufw deny 6379
ufw allow ssh
ufw allow 80
ufw allow 443
ufw allow 3000   # painel EasyPanel
ufw enable
```

---

## 11. FLUXO DE DESENVOLVIMENTO

```
Semana 1 → datahub_meta (SQL) + FastAPI base + auth JWT
Semana 2 → Rotas charts/tables com cache Redis
Semana 3 → Chatbot RAG (Groq + contexto real do banco)
Semana 4 → SvelteKit frontend + ECharts + Leaflet
Semana 5 → Worker ARQ (relatórios assíncronos)
Semana 6 → Deploy EasyPanel + testes + domínio HTTPS
```

**Fluxo de deploy contínuo:**
```
git push origin main
      ↓
EasyPanel detecta push via webhook
      ↓
Build Docker automático (sem downtime)
      ↓
Novo container sobe, antigo desce
```
