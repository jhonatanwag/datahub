# Empresas & Auth Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-step login (email+senha+company_slug → JWT) with a two-step flow (login → lista de empresas → selecionar empresa → JWT), e implementar CRUD de Empresas e Usuários com tela de configurações para admin.

**Architecture:** O backend expõe novas rotas em `auth.py`, `empresas.py` e `usuarios.py`. O frontend ganha uma nova página `/selecionar-empresa`, reforma a tela de login, atualiza o store global para `stores/auth.js` (com `isAdmin` derivado), e adiciona as páginas de configuração de admin sob `/configuracoes/empresas` e `/configuracoes/usuarios`. O guard de autenticação fica no `+layout.svelte` via `beforeNavigate` (o `hooks.client.js` proposto no spec usa sintaxe de servidor — não é válido no client; a solução equivalente em SvelteKit é o `beforeNavigate` no layout).

**Tech Stack:** FastAPI, asyncpg, bcrypt, python-jose, SvelteKit, Svelte stores

## Global Constraints

- Nunca apagar dados do banco — usar `ativo = false` para desativar
- JWT payload novo: `{ user_id, empresa_id, company_slug, nome, role, exp }`
- Logos salvas em `/data/logos/{empresa_id}.png` dentro do container backend
- Slug de empresa: único, sem espaços
- Senha sempre hasheada com bcrypt antes de salvar
- Admin não pode desativar a si mesmo
- Email único por usuário
- Ao cadastrar empresa, testar conexão com o banco antes de salvar
- `query_meta` usa `asyncpg` via pool já configurado em `config/databases.py`
- Credenciais de teste: `admin@datahub.local` / `admin123`

---

## Visão Geral dos Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `backend/routes/auth.py` | Modificar | Novo fluxo: login → empresas, selecionar-empresa → JWT |
| `backend/middleware/auth.py` | Modificar | Usar `empresa_id` (int) do JWT em vez de `company_slug` |
| `backend/routes/empresas.py` | Criar | CRUD empresas + testar conexão + logo |
| `backend/routes/usuarios.py` | Criar | CRUD usuários + vínculos de empresa |
| `backend/main.py` | Modificar | Registrar novos routers |
| `frontend/src/lib/stores/auth.js` | Criar | Store global: usuario, empresaAtiva, token, isAdmin, logout() |
| `frontend/src/lib/api.js` | Modificar | Remover company_slug do login, adicionar todos novos métodos |
| `frontend/src/routes/login/+page.svelte` | Modificar | Remover campo empresa, novo fluxo 2 etapas |
| `frontend/src/routes/selecionar-empresa/+page.svelte` | Criar | Grid de cards de empresa, auto-select se apenas 1 |
| `frontend/src/routes/+layout.svelte` | Modificar | Menu admin, topbar com empresa, beforeNavigate guard |
| `frontend/src/routes/configuracoes/empresas/+page.svelte` | Criar | Lista de empresas com editar/desativar |
| `frontend/src/routes/configuracoes/empresas/nova/+page.svelte` | Criar | Formulário nova empresa + testar conexão |
| `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte` | Criar | Formulário editar empresa |
| `frontend/src/routes/configuracoes/usuarios/+page.svelte` | Criar | Tabela de usuários |
| `frontend/src/routes/configuracoes/usuarios/novo/+page.svelte` | Criar | Formulário novo usuário + vínculos |
| `frontend/src/routes/configuracoes/usuarios/[id]/+page.svelte` | Criar | Formulário editar usuário + vínculos |

---

## Task 1: Backend — Reescrever auth.py e atualizar middleware

**Files:**
- Modify: `backend/routes/auth.py`
- Modify: `backend/middleware/auth.py`

**Interfaces:**
- Produces:
  - `POST /api/auth/login` → `{ user_id, nome, role, empresas: [{id, slug, nome, logo_url}] }`
  - `POST /api/auth/selecionar-empresa` → `{ token, token_type }`
  - `GET /api/auth/minhas-empresas` → `[{id, slug, nome, logo_url}]`
  - `GET /api/auth/me` → `{ id, nome, role, empresa_id, company_slug, company_name }`
  - JWT payload: `{ user_id, empresa_id, company_slug, nome, role, exp }`

- [ ] **Step 1: Reescrever `backend/routes/auth.py`**

Substituir o conteúdo inteiro do arquivo:

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


class SelecionarEmpresaInput(BaseModel):
    user_id: int
    empresa_id: int


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

        empresas = await query_meta("""
            SELECT e.id, e.slug, e.nome
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
            ORDER BY e.nome
        """, usuario["id"])

        return {
            "user_id": usuario["id"],
            "nome": usuario["nome"],
            "role": usuario["role"],
            "empresas": [
                {
                    "id": e["id"],
                    "slug": e["slug"],
                    "nome": e["nome"],
                    "logo_url": f"/api/empresas/{e['id']}/logo"
                }
                for e in empresas
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no login: {e}")


@router.post("/selecionar-empresa")
async def selecionar_empresa(body: SelecionarEmpresaInput):
    try:
        usuario_rows = await query_meta(
            "SELECT id, nome, role FROM usuarios WHERE id = $1 AND ativo = true",
            body.user_id
        )
        if not usuario_rows:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")

        usuario = dict(usuario_rows[0])

        acesso = await query_meta("""
            SELECT e.id, e.slug FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.id = $2 AND e.ativo = true
        """, body.user_id, body.empresa_id)

        if not acesso:
            raise HTTPException(status_code=403, detail="Sem acesso a esta empresa")

        empresa = dict(acesso[0])

        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        token = jwt.encode(
            {
                "user_id": usuario["id"],
                "empresa_id": empresa["id"],
                "company_slug": empresa["slug"],
                "nome": usuario["nome"],
                "role": usuario["role"],
                "exp": expire
            },
            settings.JWT_SECRET,
            algorithm="HS256"
        )

        return {"token": token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao selecionar empresa: {e}")


@router.get("/minhas-empresas")
async def minhas_empresas(user=Depends(get_current_user)):
    try:
        empresas = await query_meta("""
            SELECT e.id, e.slug, e.nome
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
            ORDER BY e.nome
        """, user["id"])

        return [
            {
                "id": e["id"],
                "slug": e["slug"],
                "nome": e["nome"],
                "logo_url": f"/api/empresas/{e['id']}/logo"
            }
            for e in empresas
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar empresas: {e}")


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

- [ ] **Step 2: Atualizar `backend/middleware/auth.py`**

O JWT agora carrega `empresa_id` (int). Trocar o join por `e.id = $2` em vez de `e.slug = $2`:

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

    empresa_id = payload.get("empresa_id")
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    from config.redis import get_redis
    redis = await get_redis()
    if await redis.get(f"blacklist:{payload['user_id']}"):
        raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

    rows = await query_meta("""
        SELECT u.id, u.nome, u.role,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, payload["user_id"], empresa_id)

    if not rows:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return dict(rows[0])


async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Requer perfil admin")
    return user
```

- [ ] **Step 3: Testar o backend (reiniciar container e chamar endpoints)**

```bash
docker compose -f docker-compose.dev.yml restart backend
# Aguardar ~5s e testar:

# Login novo fluxo (sem company_slug)
curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123"}' | python -m json.tool
```

Resposta esperada:
```json
{
  "user_id": 1,
  "nome": "Administrador",
  "role": "admin",
  "empresas": [
    {"id": 1, "slug": "alpha", "nome": "Empresa Alpha Ltda", "logo_url": "/api/empresas/1/logo"},
    {"id": 2, "slug": "beta",  "nome": "Beta Comércio S.A.", "logo_url": "/api/empresas/2/logo"},
    {"id": 3, "slug": "gamma", "nome": "Gamma Tech ME",      "logo_url": "/api/empresas/3/logo"}
  ]
}
```

```bash
# Selecionar empresa (substituir USER_ID e EMPRESA_ID pelos valores retornados acima)
curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"empresa_id":1}' | python -m json.tool
```

Resposta esperada: `{"token": "eyJ...", "token_type": "bearer"}`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/auth.py backend/middleware/auth.py
git commit -m "feat: two-step auth flow — login returns companies, selecionar-empresa issues JWT"
```

---

## Task 2: Backend — Criar `routes/empresas.py` e registrar no main

**Files:**
- Create: `backend/routes/empresas.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `require_admin` de `middleware/auth.py`, `query_meta` de `config/databases.py`
- Produces:
  - `GET /api/empresas/` → lista (requer admin)
  - `GET /api/empresas/{id}` → empresa por id (requer admin)
  - `POST /api/empresas/` → criar empresa (testa conexão antes)
  - `PATCH /api/empresas/{id}` → atualizar empresa
  - `DELETE /api/empresas/{id}` → desativar (ativo=false)
  - `POST /api/empresas/testar-conexao` → testa conexão asyncpg
  - `POST /api/empresas/{id}/logo` → salva PNG em `/data/logos/{id}.png`
  - `GET /api/empresas/{id}/logo` → serve PNG (público, sem auth)

- [ ] **Step 1: Criar `backend/routes/empresas.py`**

```python
import os
import asyncpg
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from config.databases import query_meta
from middleware.auth import require_admin

router = APIRouter(prefix="/api/empresas", tags=["Empresas"])

LOGOS_DIR = "/data/logos"
os.makedirs(LOGOS_DIR, exist_ok=True)


class EmpresaInput(BaseModel):
    slug: str
    nome: str
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_pass: str
    ativo: bool = True


class TestarConexaoInput(BaseModel):
    host: str
    port: int
    database: str
    user: str
    password: str


@router.get("/")
async def listar_empresas(user=Depends(require_admin)):
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, ativo, criado_em FROM empresas ORDER BY nome"
    )
    return [
        {**dict(r), "logo_url": f"/api/empresas/{r['id']}/logo"}
        for r in rows
    ]


@router.post("/testar-conexao")
async def testar_conexao(body: TestarConexaoInput, user=Depends(require_admin)):
    try:
        conn = await asyncpg.connect(
            host=body.host,
            port=body.port,
            database=body.database,
            user=body.user,
            password=body.password,
            timeout=5
        )
        result = await conn.fetchrow(
            "SELECT COUNT(*)::int AS n FROM information_schema.tables WHERE table_schema = 'public'"
        )
        await conn.close()
        return {"ok": True, "tabelas": result["n"]}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.get("/{id}")
async def buscar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, ativo, criado_em FROM empresas WHERE id = $1",
        id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    row = dict(rows[0])
    row["logo_url"] = f"/api/empresas/{id}/logo"
    return row


@router.post("/")
async def criar_empresa(body: EmpresaInput, user=Depends(require_admin)):
    try:
        conn = await asyncpg.connect(
            host=body.db_host, port=body.db_port, database=body.db_name,
            user=body.db_user, password=body.db_pass, timeout=5
        )
        await conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Conexão com o banco falhou: {e}")

    try:
        rows = await query_meta("""
            INSERT INTO empresas (slug, nome, db_host, db_port, db_name, db_user, db_pass, ativo)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")


@router.patch("/{id}")
async def atualizar_empresa(id: int, body: EmpresaInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    try:
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6, db_pass=$7, ativo=$8
            WHERE id=$9
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")


@router.delete("/{id}")
async def desativar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    await query_meta("UPDATE empresas SET ativo = false WHERE id = $1", id)
    return {"ok": True}


@router.post("/{id}/logo")
async def upload_logo(id: int, file: UploadFile = File(...), user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    content = await file.read()
    with open(f"{LOGOS_DIR}/{id}.png", "wb") as f:
        f.write(content)
    return {"ok": True, "logo_url": f"/api/empresas/{id}/logo"}


@router.get("/{id}/logo")
async def get_logo(id: int):
    logo_path = f"{LOGOS_DIR}/{id}.png"
    if not os.path.exists(logo_path):
        raise HTTPException(status_code=404, detail="Logo não encontrado")
    return FileResponse(logo_path, media_type="image/png")
```

- [ ] **Step 2: Registrar router em `backend/main.py`**

Adicionar import e `include_router`:

```python
# Na linha dos imports:
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios

# Após os outros include_router:
app.include_router(empresas.router)
app.include_router(usuarios.router)
```

> Nota: `usuarios` ainda não existe — será criado na Task 3. Por ora, adicione só o import e include de `empresas`.

Ou seja, na Task 2, o `main.py` fica:

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from config.databases import get_meta_pool, close_all_pools
from config.redis import get_redis
from routes import auth, charts, tables, ai, reports, queries, empresas

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
app.include_router(empresas.router)


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

- [ ] **Step 3: Testar as rotas de empresa**

```bash
docker compose -f docker-compose.dev.yml restart backend
# Aguardar ~5s

# Login para obter token
TOKEN=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123"}' \
  | python -c "import sys,json; d=json.load(sys.stdin); t=d['empresas'][0]['id']; print(t)")

# Selecionar empresa 1 para obter JWT
JWT=$(curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"empresa_id":1}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Listar empresas (requer admin)
curl -s http://localhost:3001/api/empresas/ \
  -H "Authorization: Bearer $JWT" | python -m json.tool
```

Resposta esperada: array com 3 empresas (alpha, beta, gamma).

```bash
# Testar conexão
curl -s -X POST http://localhost:3001/api/empresas/testar-conexao \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"host":"postgres","port":5432,"database":"datahub_meta","user":"datahub_user","password":"datahub123"}' \
  | python -m json.tool
```

Resposta esperada: `{"ok": true, "tabelas": 8}`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/empresas.py backend/main.py
git commit -m "feat: add empresas CRUD routes with connection test and logo upload"
```

---

## Task 3: Backend — Criar `routes/usuarios.py` e finalizar main.py

**Files:**
- Create: `backend/routes/usuarios.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `require_admin`, `get_current_user` de `middleware/auth.py`
- Produces:
  - `GET /api/usuarios/` → lista com empresas vinculadas
  - `POST /api/usuarios/` → criar + senha hasheada
  - `PATCH /api/usuarios/{id}` → atualizar
  - `DELETE /api/usuarios/{id}` → desativar (não pode desativar a si mesmo)
  - `POST /api/usuarios/{id}/empresas` → substituir vínculos
  - `GET /api/usuarios/{id}/empresas` → listar vínculos
  - `DELETE /api/usuarios/{id}/empresas/{empresa_id}` → remover vínculo

- [ ] **Step 1: Criar `backend/routes/usuarios.py`**

```python
import bcrypt
import asyncpg
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from config.databases import query_meta
from middleware.auth import require_admin

router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])


class UsuarioInput(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "viewer"
    ativo: bool = True


class VincularEmpresasInput(BaseModel):
    empresa_ids: List[int]


@router.get("/")
async def listar_usuarios(user=Depends(require_admin)):
    usuarios = await query_meta(
        "SELECT id, nome, email, role, ativo, criado_em FROM usuarios ORDER BY nome"
    )
    result = []
    for u in usuarios:
        empresas = await query_meta("""
            SELECT e.id, e.nome, e.slug
            FROM empresas e
            JOIN usuario_empresas ue ON ue.empresa_id = e.id
            WHERE ue.usuario_id = $1 AND e.ativo = true
        """, u["id"])
        result.append({**dict(u), "empresas": [dict(e) for e in empresas]})
    return result


@router.post("/")
async def criar_usuario(body: UsuarioInput, user=Depends(require_admin)):
    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
    try:
        rows = await query_meta("""
            INSERT INTO usuarios (nome, email, senha_hash, role, ativo)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, nome, email, role, ativo
        """, body.nome, body.email, senha_hash, body.role, body.ativo)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email já está em uso")


@router.patch("/{id}")
async def atualizar_usuario(id: int, body: UsuarioInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
    try:
        rows = await query_meta("""
            UPDATE usuarios
            SET nome=$1, email=$2, senha_hash=$3, role=$4, ativo=$5
            WHERE id=$6
            RETURNING id, nome, email, role, ativo
        """, body.nome, body.email, senha_hash, body.role, body.ativo, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email já está em uso")


@router.delete("/{id}")
async def desativar_usuario(id: int, user=Depends(require_admin)):
    if id == user["id"]:
        raise HTTPException(status_code=400, detail="Não é possível desativar o próprio usuário")
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    await query_meta("UPDATE usuarios SET ativo = false WHERE id = $1", id)
    return {"ok": True}


@router.post("/{id}/empresas")
async def vincular_empresas(id: int, body: VincularEmpresasInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    await query_meta("DELETE FROM usuario_empresas WHERE usuario_id = $1", id)
    for empresa_id in body.empresa_ids:
        await query_meta(
            "INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            id, empresa_id
        )
    return {"ok": True, "empresa_ids": body.empresa_ids}


@router.get("/{id}/empresas")
async def listar_empresas_usuario(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    empresas = await query_meta("""
        SELECT e.id, e.slug, e.nome, e.ativo
        FROM empresas e
        JOIN usuario_empresas ue ON ue.empresa_id = e.id
        WHERE ue.usuario_id = $1
        ORDER BY e.nome
    """, id)
    return [dict(e) for e in empresas]


@router.delete("/{id}/empresas/{empresa_id}")
async def remover_vinculo(id: int, empresa_id: int, user=Depends(require_admin)):
    await query_meta(
        "DELETE FROM usuario_empresas WHERE usuario_id = $1 AND empresa_id = $2",
        id, empresa_id
    )
    return {"ok": True}
```

- [ ] **Step 2: Atualizar `backend/main.py` para incluir usuarios**

```python
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios

# Adicionar após empresas.router:
app.include_router(usuarios.router)
```

O `main.py` completo após esta task:

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from config.databases import get_meta_pool, close_all_pools
from config.redis import get_redis
from routes import auth, charts, tables, ai, reports, queries, empresas, usuarios

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
app.include_router(empresas.router)
app.include_router(usuarios.router)


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

- [ ] **Step 3: Testar rotas de usuário**

```bash
docker compose -f docker-compose.dev.yml restart backend
# Aguardar ~5s

JWT=$(curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@datahub.local","senha":"admin123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['empresas'][0]['id'])" \
  && curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"empresa_id":1}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Listar usuários
curl -s http://localhost:3001/api/usuarios/ \
  -H "Authorization: Bearer $JWT" | python -m json.tool
```

Resposta esperada: lista com 1 usuário (Administrador) e suas 3 empresas vinculadas.

```bash
# Criar novo usuário
curl -s -X POST http://localhost:3001/api/usuarios/ \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"nome":"Teste Viewer","email":"viewer@datahub.local","senha":"viewer123","role":"viewer"}' \
  | python -m json.tool
```

Resposta esperada: `{"id": 2, "nome": "Teste Viewer", "email": "viewer@datahub.local", "role": "viewer", "ativo": true}`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/usuarios.py backend/main.py
git commit -m "feat: add usuarios CRUD routes with company links management"
```

---

## Task 4: Frontend — Criar `stores/auth.js` e atualizar `api.js`

**Files:**
- Create: `frontend/src/lib/stores/auth.js`
- Modify: `frontend/src/lib/api.js`

**Interfaces:**
- Produces (auth.js):
  - `usuario` — writable store: `{ id, nome, role, empresa_id, company_slug, company_name } | null`
  - `empresaAtiva` — writable store: `{ id, slug, nome, logo_url } | null`
  - `token` — writable store: `string | null`
  - `isAdmin` — derived store: `boolean`
  - `logout()` — limpa os 3 stores e localStorage
- Produces (api.js novos métodos):
  - `api.login(email, senha)` — sem company_slug
  - `api.selecionarEmpresa(user_id, empresa_id)`
  - `api.minhasEmpresas()`
  - `api.listarEmpresas()`, `api.buscarEmpresa(id)`, `api.criarEmpresa(data)`, `api.atualizarEmpresa(id, data)`, `api.desativarEmpresa(id)`
  - `api.testarConexao(data)`
  - `api.uploadLogo(id, formData)`
  - `api.listarUsuarios()`, `api.criarUsuario(data)`, `api.atualizarUsuario(id, data)`, `api.desativarUsuario(id)`
  - `api.vincularEmpresas(id, empresa_ids)`

- [ ] **Step 1: Criar `frontend/src/lib/stores/auth.js`**

```javascript
import { writable, derived } from 'svelte/store';

function safeGet(key, fallback) {
    if (typeof localStorage === 'undefined') return fallback;
    try { return JSON.parse(localStorage.getItem(key) ?? JSON.stringify(fallback)); }
    catch { return fallback; }
}

export const usuario     = writable(safeGet('usuario', null));
export const empresaAtiva = writable(safeGet('empresaAtiva', null));
export const token       = writable(typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null);

export const isAdmin = derived(usuario, $u => $u?.role === 'admin');

if (typeof localStorage !== 'undefined') {
    usuario.subscribe(v => localStorage.setItem('usuario', JSON.stringify(v)));
    empresaAtiva.subscribe(v => localStorage.setItem('empresaAtiva', JSON.stringify(v)));
    token.subscribe(v => v ? localStorage.setItem('token', v) : localStorage.removeItem('token'));
}

export function logout() {
    usuario.set(null);
    empresaAtiva.set(null);
    token.set(null);
}
```

- [ ] **Step 2: Substituir `frontend/src/lib/api.js`**

```javascript
const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
    const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
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
    login: (email, senha) =>
        request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, senha }) }),

    selecionarEmpresa: (user_id, empresa_id) =>
        request('/api/auth/selecionar-empresa', {
            method: 'POST',
            body: JSON.stringify({ user_id, empresa_id })
        }),

    minhasEmpresas: () => request('/api/auth/minhas-empresas'),
    me: () => request('/api/auth/me'),

    logout: () => request('/api/auth/logout', { method: 'POST' }),

    // Charts
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
    perguntarIA: (pergunta) =>
        request('/api/ai/ask', { method: 'POST', body: JSON.stringify({ pergunta }) }),
    historicoIA: () => request('/api/ai/historico'),

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
    buscarQuery:    (id)       => request(`/api/queries/${id}`),
    criarQuery:     (data)     => request('/api/queries/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarQuery: (id, data) => request(`/api/queries/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    deletarQuery:   (id)       => request(`/api/queries/${id}`, { method: 'DELETE' }),
    testarQuery:    (data)     => request('/api/queries/testar', { method: 'POST', body: JSON.stringify(data) }),
    executarQuery:  (slug, params = {}) => {
        const p = new URLSearchParams(params);
        return request(`/api/queries/executar/${slug}?${p}`);
    },
    layoutDashboard: () => request('/api/queries/layout/dashboard'),

    // Empresas (admin)
    listarEmpresas:   ()         => request('/api/empresas/'),
    buscarEmpresa:    (id)       => request(`/api/empresas/${id}`),
    criarEmpresa:     (data)     => request('/api/empresas/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarEmpresa: (id, data) => request(`/api/empresas/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    desativarEmpresa: (id)       => request(`/api/empresas/${id}`, { method: 'DELETE' }),
    testarConexao:    (data)     => request('/api/empresas/testar-conexao', { method: 'POST', body: JSON.stringify(data) }),

    uploadLogo: (id, formData) => {
        const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
        return fetch(`${BASE}/api/empresas/${id}/logo`, {
            method: 'POST',
            headers: tok ? { Authorization: `Bearer ${tok}` } : {},
            body: formData,
        }).then(r => r.json());
    },

    // Usuários (admin)
    listarUsuarios:   ()               => request('/api/usuarios/'),
    criarUsuario:     (data)           => request('/api/usuarios/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarUsuario: (id, data)       => request(`/api/usuarios/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    desativarUsuario: (id)             => request(`/api/usuarios/${id}`, { method: 'DELETE' }),
    vincularEmpresas: (id, empresa_ids) =>
        request(`/api/usuarios/${id}/empresas`, { method: 'POST', body: JSON.stringify({ empresa_ids }) }),
    listarEmpresasUsuario: (id)        => request(`/api/usuarios/${id}/empresas`),
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/stores/auth.js frontend/src/lib/api.js
git commit -m "feat: add auth store with isAdmin derived and update api.js with new endpoints"
```

---

## Task 5: Frontend — Reescrever tela de login

**Files:**
- Modify: `frontend/src/routes/login/+page.svelte`

**Interfaces:**
- Consumes: `api.login(email, senha)` → `{ user_id, nome, role, empresas }`
- Produces: salva `temp_user` em `sessionStorage` e redireciona para `/selecionar-empresa`

- [ ] **Step 1: Reescrever `frontend/src/routes/login/+page.svelte`**

```svelte
<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let email      = '';
  let senha      = '';
  let erro       = '';
  let carregando = false;

  async function login() {
    erro = '';
    carregando = true;
    try {
      const res = await api.login(email, senha);
      sessionStorage.setItem('temp_user', JSON.stringify({
        user_id: res.user_id,
        nome: res.nome,
        role: res.role,
        empresas: res.empresas
      }));
      goto('/selecionar-empresa');
    } catch {
      erro = 'E-mail ou senha inválidos.';
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

    <label>
      E-mail
      <input type="email" bind:value={email} on:keydown={onKeydown} placeholder="admin@datahub.local" />
    </label>

    <label>
      Senha
      <input type="password" bind:value={senha} on:keydown={onKeydown} placeholder="••••••••" />
    </label>

    {#if erro}<p class="error">{erro}</p>{/if}

    <button class="btn-primary" on:click={login} disabled={carregando}>
      {carregando ? 'Entrando...' : 'Entrar'}
    </button>
  </div>
</div>

<style>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.login-box {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
h1 { font-family: var(--font-display); font-size: 28px; color: var(--accent); }
.subtitle { color: var(--muted); margin-top: -10px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
button { margin-top: 8px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

- [ ] **Step 2: Testar no browser**

Abrir http://localhost:3000/login e verificar:
- Não aparece campo de empresa
- Login com `admin@datahub.local` / `admin123` redireciona para `/selecionar-empresa`
- Login com senha errada exibe "E-mail ou senha inválidos."

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/login/+page.svelte
git commit -m "feat: simplify login page — remove company field, redirect to selecionar-empresa"
```

---

## Task 6: Frontend — Criar tela `/selecionar-empresa`

**Files:**
- Create: `frontend/src/routes/selecionar-empresa/+page.svelte`

**Interfaces:**
- Consumes: `sessionStorage.temp_user` `{ user_id, nome, role, empresas }`, `api.selecionarEmpresa(user_id, empresa_id)` → `{ token }`
- Produces: seta `token`, `usuario`, `empresaAtiva` nos stores e redireciona para `/`

- [ ] **Step 1: Criar `frontend/src/routes/selecionar-empresa/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { token, usuario, empresaAtiva } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';

  let nomeUsuario = '';
  let empresas    = [];
  let erro        = '';
  let carregando  = false;

  onMount(() => {
    const raw = typeof sessionStorage !== 'undefined'
      ? sessionStorage.getItem('temp_user')
      : null;
    if (!raw) { goto('/login'); return; }

    const tempUser = JSON.parse(raw);
    nomeUsuario = tempUser.nome;
    empresas    = tempUser.empresas;

    if (empresas.length === 1) selecionar(empresas[0]);
  });

  async function selecionar(empresa) {
    const raw = sessionStorage.getItem('temp_user');
    if (!raw) { goto('/login'); return; }
    const tempUser = JSON.parse(raw);

    carregando = true;
    erro = '';
    try {
      const res = await api.selecionarEmpresa(tempUser.user_id, empresa.id);
      token.set(res.token);
      // Fetch full user profile (includes role from JWT-validated session)
      const me = await api.me();
      usuario.set(me);
      empresaAtiva.set({ id: empresa.id, slug: empresa.slug, nome: empresa.nome, logo_url: empresa.logo_url });
      sessionStorage.removeItem('temp_user');
      goto('/');
    } catch {
      erro = 'Erro ao selecionar empresa. Tente novamente.';
      carregando = false;
    }
  }

  function sair() {
    sessionStorage.removeItem('temp_user');
    goto('/login');
  }

  function inicial(nome) {
    return nome?.charAt(0)?.toUpperCase() ?? '?';
  }
</script>

<svelte:head><title>Selecionar Empresa — DataHub</title></svelte:head>

<div class="wrap">
  <div class="header">
    <h2>Olá, {nomeUsuario}! Selecione a empresa:</h2>
    <button class="btn-ghost" on:click={sair}>Sair</button>
  </div>

  {#if erro}<p class="error">{erro}</p>{/if}

  <div class="grid">
    {#each empresas as empresa}
      <button
        class="card empresa-card"
        on:click={() => selecionar(empresa)}
        disabled={carregando}
      >
        <div class="logo-wrap">
          <img
            src={empresa.logo_url}
            alt={empresa.nome}
            on:error={(e) => { e.target.style.display = 'none'; e.target.nextElementSibling.style.display = 'flex'; }}
          />
          <div class="logo-inicial" style="display:none">{inicial(empresa.nome)}</div>
        </div>
        <span class="empresa-nome">{empresa.nome}</span>
      </button>
    {/each}
  </div>
</div>

<style>
.wrap {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 32px;
}
.header {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 32px;
}
h2 { font-size: 20px; color: var(--text); }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
  width: 100%;
  max-width: 720px;
}
.empresa-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 16px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color .15s, transform .1s;
  text-align: center;
}
.empresa-card:hover { border-color: var(--accent-blue); transform: translateY(-2px); }
.logo-wrap { width: 64px; height: 64px; position: relative; }
.logo-wrap img { width: 64px; height: 64px; object-fit: contain; border-radius: 8px; }
.logo-inicial {
  width: 64px; height: 64px;
  background: var(--accent);
  color: white;
  font-size: 28px;
  font-weight: 700;
  border-radius: 8px;
  align-items: center;
  justify-content: center;
}
.empresa-nome { font-size: 14px; color: var(--text); font-weight: 500; }
.error { color: var(--danger, #f85149); margin-bottom: 16px; }
</style>
```

- [ ] **Step 2: Testar no browser**

1. Ir para http://localhost:3000/login
2. Logar com `admin@datahub.local` / `admin123`
3. Verificar que redireciona para `/selecionar-empresa` com 3 cards de empresa
4. Clicar numa empresa e verificar redirecionamento para `/`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/selecionar-empresa/+page.svelte
git commit -m "feat: add selecionar-empresa page with company cards and auto-select for single company"
```

---

## Task 7: Frontend — Atualizar `+layout.svelte` (menu admin, topbar, auth guard)

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`

**Interfaces:**
- Consumes: `usuario`, `empresaAtiva`, `token`, `isAdmin`, `logout()` de `$lib/stores/auth.js`
- Rotas públicas (sem layout): `/login`, `/selecionar-empresa`
- Guard: se sem token e rota não pública → redirecionar para `/login`

- [ ] **Step 1: Reescrever `frontend/src/routes/+layout.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { goto, beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { token, usuario, empresaAtiva, isAdmin, logout } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';
  import '../app.css';

  const PUBLIC_ROUTES = ['/login', '/selecionar-empresa'];

  let sidebarOpen = true;

  const navLinks = [
    { href: '/',                      label: 'Dashboard'  },
    { href: '/ai',                    label: 'IA / Chat'  },
  ];

  const adminLinks = [
    { href: '/configuracoes/empresas', label: 'Empresas'  },
    { href: '/configuracoes/usuarios', label: 'Usuários'  },
    { href: '/configuracoes/queries',  label: 'Queries'   },
  ];

  onMount(async () => {
    const path = $page.url.pathname;
    if (PUBLIC_ROUTES.includes(path)) return;

    const tok = localStorage.getItem('token');
    if (!tok) { goto('/login'); return; }

    if (!$usuario) {
      try {
        const me = await api.me();
        usuario.set(me);
        if (!$empresaAtiva) {
          empresaAtiva.set({
            id: me.empresa_id,
            slug: me.company_slug,
            nome: me.company_name,
            logo_url: `/api/empresas/${me.empresa_id}/logo`
          });
        }
      } catch {
        localStorage.removeItem('token');
        token.set(null);
        goto('/login');
      }
    }
  });

  beforeNavigate(({ to }) => {
    const path = to?.url?.pathname ?? '';
    if (PUBLIC_ROUTES.includes(path)) return;
    const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
    if (!tok) goto('/login');
  });

  async function handleLogout() {
    await api.logout().catch(() => {});
    logout();
    goto('/login');
  }

  function trocarEmpresa() {
    goto('/selecionar-empresa');
  }

  function isActive(href) {
    return $page.url.pathname === href || $page.url.pathname.startsWith(href + '/');
  }
</script>

{#if PUBLIC_ROUTES.includes($page.url.pathname)}
  <slot />
{:else}
  <div class="shell">
    <nav class="sidebar" class:collapsed={!sidebarOpen}>
      <div class="sidebar-header">
        <span class="logo">DataHub</span>
        <button class="btn-ghost icon-btn" on:click={() => sidebarOpen = !sidebarOpen}>≡</button>
      </div>

      <ul class="nav-links">
        {#each navLinks as link}
          <li class:active={isActive(link.href)}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}

        {#if $isAdmin}
          <li class="nav-section">Admin</li>
          {#each adminLinks as link}
            <li class:active={isActive(link.href)}>
              <a href={link.href}>{link.label}</a>
            </li>
          {/each}
        {/if}
      </ul>

      <button class="btn-ghost logout" on:click={handleLogout}>Sair</button>
    </nav>

    <div class="main-wrap">
      <header class="topbar">
        <div class="topbar-empresa">
          <img
            src={$empresaAtiva?.logo_url}
            alt={$empresaAtiva?.nome}
            class="empresa-logo"
            on:error={(e) => { e.target.style.display='none'; }}
          />
          <span class="empresa-nome">{$empresaAtiva?.nome ?? ''}</span>
          <button class="btn-ghost btn-sm" on:click={trocarEmpresa}>Trocar empresa</button>
        </div>
        <div class="topbar-user">
          <span class="user-avatar">{$usuario?.nome?.charAt(0)?.toUpperCase() ?? '?'}</span>
          <span class="user-nome">{$usuario?.nome ?? ''}</span>
        </div>
      </header>

      <main class="content">
        <slot />
      </main>
    </div>
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

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px 16px;
}
.logo { font-family: var(--font-display); font-size: 16px; color: var(--accent); font-weight: 500; }

.nav-links { list-style: none; flex: 1; padding: 0; margin: 0; }
.nav-links li a {
  display: block; padding: 10px 20px;
  color: var(--muted); font-size: 14px;
}
.nav-links li.active a {
  color: var(--text);
  background: var(--surface2);
  border-left: 2px solid var(--accent-blue);
}
.nav-links li a:hover { color: var(--text); background: var(--surface2); text-decoration: none; }

.nav-section {
  padding: 16px 20px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
}

.logout { margin: 8px 12px 0; width: calc(100% - 24px); }
.icon-btn { padding: 4px 8px; }

.main-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 52px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.topbar-empresa {
  display: flex;
  align-items: center;
  gap: 10px;
}
.empresa-logo {
  width: 28px; height: 28px;
  object-fit: contain;
  border-radius: 4px;
}
.empresa-nome { font-size: 14px; font-weight: 500; color: var(--text); }
.btn-sm { font-size: 12px; padding: 4px 10px; }

.topbar-user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.user-nome { font-size: 13px; color: var(--muted); }

.content { flex: 1; overflow-y: auto; }
</style>
```

- [ ] **Step 2: Testar no browser**

1. Logar e selecionar empresa → verificar topbar com nome da empresa
2. Verificar que admin vê seção "Admin" com Empresas / Usuários / Queries
3. Clicar "Trocar empresa" → vai para `/selecionar-empresa`
4. Clicar "Sair" → limpa token e vai para `/login`
5. Tentar acessar `/` sem token → redireciona para `/login`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "feat: update layout with admin menu, topbar with company switcher, auth guard"
```

---

## Task 8: Frontend — Tela `/configuracoes/empresas`

**Files:**
- Create: `frontend/src/routes/configuracoes/empresas/+page.svelte`
- Create: `frontend/src/routes/configuracoes/empresas/nova/+page.svelte`
- Create: `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`

**Interfaces:**
- Consumes: `api.listarEmpresas()`, `api.desativarEmpresa(id)`, `api.criarEmpresa(data)`, `api.atualizarEmpresa(id, data)`, `api.testarConexao(data)`, `api.uploadLogo(id, formData)`

- [ ] **Step 1: Criar `frontend/src/routes/configuracoes/empresas/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let empresas   = [];
  let carregando = true;
  let erro       = null;

  onMount(async () => {
    try {
      empresas = await api.listarEmpresas();
    } catch (e) {
      erro = 'Erro ao carregar empresas.';
    } finally {
      carregando = false;
    }
  });

  async function desativar(id) {
    if (!confirm('Desativar esta empresa?')) return;
    try {
      await api.desativarEmpresa(id);
      empresas = empresas.map(e => e.id === id ? { ...e, ativo: false } : e);
    } catch {
      alert('Erro ao desativar empresa.');
    }
  }

  function inicial(nome) {
    return nome?.charAt(0)?.toUpperCase() ?? '?';
  }
</script>

<svelte:head><title>Empresas — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Empresas</h2>
    <a href="/configuracoes/empresas/nova" class="btn-primary">+ Nova Empresa</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <div class="grid">
      {#each empresas as empresa}
        <div class="card empresa-card" class:inativo={!empresa.ativo}>
          <div class="card-logo">
            <img
              src={empresa.logo_url}
              alt={empresa.nome}
              on:error={(e) => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex'; }}
            />
            <div class="logo-inicial" style="display:none">{inicial(empresa.nome)}</div>
          </div>
          <div class="card-info">
            <strong>{empresa.nome}</strong>
            <span class="muted">{empresa.slug}</span>
            <span class="badge" class:ativo={empresa.ativo}>{empresa.ativo ? 'Ativo' : 'Inativo'}</span>
          </div>
          <div class="card-actions">
            <a href="/configuracoes/empresas/{empresa.id}" class="btn-ghost btn-sm">Editar</a>
            {#if empresa.ativo}
              <button class="btn-ghost btn-sm danger" on:click={() => desativar(empresa.id)}>Desativar</button>
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
h2 { font-size: 20px; color: var(--text); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.empresa-card { display: flex; align-items: center; gap: 16px; padding: 16px; }
.empresa-card.inativo { opacity: .5; }
.card-logo { width: 48px; height: 48px; flex-shrink: 0; }
.card-logo img { width: 48px; height: 48px; object-fit: contain; border-radius: 6px; }
.logo-inicial {
  width: 48px; height: 48px;
  background: var(--accent); color: white;
  font-size: 22px; font-weight: 700;
  border-radius: 6px;
  align-items: center; justify-content: center;
}
.card-info { flex: 1; display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.card-info strong { color: var(--text); }
.card-actions { display: flex; gap: 8px; flex-direction: column; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.badge.ativo { background: #1a4731; color: #3fb950; }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
```

- [ ] **Step 2: Criar `frontend/src/routes/configuracoes/empresas/nova/+page.svelte`**

```svelte
<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let nome    = '';
  let slug    = '';
  let db_host = '';
  let db_port = 5432;
  let db_name = '';
  let db_user = '';
  let db_pass = '';
  let logoFile = null;

  let testeStatus  = null; // null | 'ok' | 'fail'
  let testeMensagem = '';
  let testando     = false;
  let salvando     = false;
  let erro         = '';

  function gerarSlug() {
    slug = nome.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
  }

  async function testarConexao() {
    testando = true;
    testeStatus = null;
    try {
      const res = await api.testarConexao({ host: db_host, port: db_port, database: db_name, user: db_user, password: db_pass });
      if (res.ok) {
        testeStatus = 'ok';
        testeMensagem = `Conexão OK — ${res.tabelas} tabelas encontradas`;
      } else {
        testeStatus = 'fail';
        testeMensagem = `Falha: ${res.erro}`;
      }
    } catch {
      testeStatus = 'fail';
      testeMensagem = 'Erro ao testar conexão.';
    } finally {
      testando = false;
    }
  }

  async function salvar() {
    erro = '';
    salvando = true;
    try {
      const empresa = await api.criarEmpresa({ slug, nome, db_host, db_port, db_name, db_user, db_pass });
      if (logoFile) {
        const fd = new FormData();
        fd.append('file', logoFile);
        await api.uploadLogo(empresa.id, fd);
      }
      goto('/configuracoes/empresas');
    } catch (e) {
      erro = e.message || 'Erro ao salvar empresa.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Empresa — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Nova Empresa</h2>
    <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
  </div>

  <div class="form card">
    <section>
      <h3>Dados da Empresa</h3>
      <label>
        Nome da empresa
        <input bind:value={nome} on:input={gerarSlug} placeholder="Empresa Exemplo Ltda" />
      </label>
      <label>
        Slug (identificador único)
        <input bind:value={slug} placeholder="empresa-exemplo" />
      </label>
      <label>
        Logo
        <input type="file" accept="image/*" on:change={(e) => logoFile = e.target.files[0]} />
        {#if logoFile}
          <img class="logo-preview" src={URL.createObjectURL(logoFile)} alt="preview" />
        {/if}
      </label>
    </section>

    <section>
      <h3>Conexão com o Banco</h3>
      <label>Host <input bind:value={db_host} placeholder="db.example.com" /></label>
      <div class="row">
        <label style="flex:1">Porta <input type="number" bind:value={db_port} /></label>
        <label style="flex:2">Banco <input bind:value={db_name} /></label>
      </div>
      <label>Usuário <input bind:value={db_user} /></label>
      <label>Senha <input type="password" bind:value={db_pass} /></label>

      <button class="btn-secondary" on:click={testarConexao} disabled={testando || !db_host || !db_name}>
        {testando ? 'Testando...' : 'Testar Conexão'}
      </button>

      {#if testeStatus === 'ok'}
        <p class="ok">{testeMensagem}</p>
      {:else if testeStatus === 'fail'}
        <p class="error">{testeMensagem}</p>
      {/if}
    </section>

    {#if erro}<p class="error">{erro}</p>{/if}

    <div class="actions">
      <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" on:click={salvar} disabled={salvando || testeStatus !== 'ok'}>
        {salvando ? 'Salvando...' : 'Salvar Empresa'}
      </button>
    </div>
  </div>
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); }
h3 { font-size: 15px; color: var(--text); margin: 0 0 16px; }
.form { max-width: 560px; display: flex; flex-direction: column; gap: 32px; padding: 24px; }
section { display: flex; flex-direction: column; gap: 12px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.row { display: flex; gap: 12px; }
.logo-preview { width: 80px; height: 80px; object-fit: contain; border-radius: 8px; margin-top: 8px; border: 1px solid var(--border); }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.ok { color: #3fb950; font-size: 13px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

- [ ] **Step 3: Criar `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`**

```svelte
<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let empresa = null;
  let logoFile = null;
  let testeStatus = null;
  let testeMensagem = '';
  let testando  = false;
  let salvando  = false;
  let erro      = '';

  onMount(async () => {
    try {
      empresa = await api.buscarEmpresa(Number($page.params.id));
    } catch {
      goto('/configuracoes/empresas');
    }
  });

  async function testarConexao() {
    testando = true;
    testeStatus = null;
    try {
      const res = await api.testarConexao({
        host: empresa.db_host, port: empresa.db_port,
        database: empresa.db_name, user: empresa.db_user, password: empresa.db_pass
      });
      testeStatus = res.ok ? 'ok' : 'fail';
      testeMensagem = res.ok ? `Conexão OK — ${res.tabelas} tabelas` : `Falha: ${res.erro}`;
    } catch {
      testeStatus = 'fail';
      testeMensagem = 'Erro ao testar conexão.';
    } finally {
      testando = false;
    }
  }

  async function salvar() {
    erro = '';
    salvando = true;
    try {
      await api.atualizarEmpresa(empresa.id, {
        slug: empresa.slug, nome: empresa.nome,
        db_host: empresa.db_host, db_port: empresa.db_port,
        db_name: empresa.db_name, db_user: empresa.db_user, db_pass: empresa.db_pass,
        ativo: empresa.ativo
      });
      if (logoFile) {
        const fd = new FormData();
        fd.append('file', logoFile);
        await api.uploadLogo(empresa.id, fd);
      }
      goto('/configuracoes/empresas');
    } catch (e) {
      erro = e.message || 'Erro ao salvar.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Editar Empresa — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Editar Empresa</h2>
    <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
  </div>

  {#if empresa}
    <div class="form card">
      <section>
        <h3>Dados da Empresa</h3>
        <label>Nome <input bind:value={empresa.nome} /></label>
        <label>Slug <input bind:value={empresa.slug} /></label>
        <label>
          Logo
          <input type="file" accept="image/*" on:change={(e) => logoFile = e.target.files[0]} />
          {#if logoFile}
            <img class="logo-preview" src={URL.createObjectURL(logoFile)} alt="preview" />
          {:else}
            <img class="logo-preview" src={empresa.logo_url} alt={empresa.nome} on:error={(e) => e.target.style.display='none'} />
          {/if}
        </label>
      </section>

      <section>
        <h3>Conexão com o Banco</h3>
        <label>Host <input bind:value={empresa.db_host} /></label>
        <div class="row">
          <label style="flex:1">Porta <input type="number" bind:value={empresa.db_port} /></label>
          <label style="flex:2">Banco <input bind:value={empresa.db_name} /></label>
        </div>
        <label>Usuário <input bind:value={empresa.db_user} /></label>
        <label>Senha <input type="password" bind:value={empresa.db_pass} /></label>

        <button class="btn-secondary" on:click={testarConexao} disabled={testando}>
          {testando ? 'Testando...' : 'Testar Conexão'}
        </button>
        {#if testeStatus === 'ok'}<p class="ok">{testeMensagem}</p>{/if}
        {#if testeStatus === 'fail'}<p class="error">{testeMensagem}</p>{/if}
      </section>

      {#if erro}<p class="error">{erro}</p>{/if}

      <div class="actions">
        <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
        <button class="btn-primary" on:click={salvar} disabled={salvando}>
          {salvando ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </div>
    </div>
  {:else}
    <p class="muted">Carregando...</p>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); }
h3 { font-size: 15px; color: var(--text); margin: 0 0 16px; }
.form { max-width: 560px; display: flex; flex-direction: column; gap: 32px; padding: 24px; }
section { display: flex; flex-direction: column; gap: 12px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.row { display: flex; gap: 12px; }
.logo-preview { width: 80px; height: 80px; object-fit: contain; border-radius: 8px; margin-top: 8px; border: 1px solid var(--border); }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.ok { color: #3fb950; font-size: 13px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }
</style>
```

- [ ] **Step 4: Testar no browser**

1. Acessar http://localhost:3000/configuracoes/empresas (como admin)
2. Verificar lista com 3 cards de empresa
3. Clicar "+ Nova Empresa" → formulário abre
4. Testar conexão com dados reais → botão "Salvar Empresa" habilita
5. Salvar empresa → volta para lista

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/configuracoes/empresas/
git commit -m "feat: add configuracoes/empresas pages — list, create, edit with connection test"
```

---

## Task 9: Frontend — Tela `/configuracoes/usuarios`

**Files:**
- Create: `frontend/src/routes/configuracoes/usuarios/+page.svelte`
- Create: `frontend/src/routes/configuracoes/usuarios/novo/+page.svelte`
- Create: `frontend/src/routes/configuracoes/usuarios/[id]/+page.svelte`

**Interfaces:**
- Consumes: `api.listarUsuarios()`, `api.desativarUsuario(id)`, `api.criarUsuario(data)`, `api.atualizarUsuario(id, data)`, `api.vincularEmpresas(id, empresa_ids)`, `api.listarEmpresas()`

- [ ] **Step 1: Criar `frontend/src/routes/configuracoes/usuarios/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let usuarios   = [];
  let carregando = true;
  let erro       = null;

  onMount(async () => {
    try {
      usuarios = await api.listarUsuarios();
    } catch {
      erro = 'Erro ao carregar usuários.';
    } finally {
      carregando = false;
    }
  });

  async function desativar(id) {
    if (!confirm('Desativar este usuário?')) return;
    try {
      await api.desativarUsuario(id);
      usuarios = usuarios.map(u => u.id === id ? { ...u, ativo: false } : u);
    } catch (e) {
      alert(e.message || 'Erro ao desativar.');
    }
  }
</script>

<svelte:head><title>Usuários — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Usuários</h2>
    <a href="/configuracoes/usuarios/novo" class="btn-primary">+ Novo Usuário</a>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else if erro}
    <p class="error">{erro}</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Nome</th>
          <th>E-mail</th>
          <th>Perfil</th>
          <th>Status</th>
          <th>Empresas</th>
          <th>Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each usuarios as u}
          <tr class:inativo={!u.ativo}>
            <td>{u.nome}</td>
            <td>{u.email}</td>
            <td><span class="badge role-{u.role}">{u.role === 'admin' ? 'Admin' : 'Visualizador'}</span></td>
            <td><span class="badge" class:ativo={u.ativo}>{u.ativo ? 'Ativo' : 'Inativo'}</span></td>
            <td class="empresas-cell">{u.empresas?.map(e => e.slug).join(', ') || '—'}</td>
            <td class="actions-cell">
              <a href="/configuracoes/usuarios/{u.id}" class="btn-ghost btn-sm">Editar</a>
              {#if u.ativo}
                <button class="btn-ghost btn-sm danger" on:click={() => desativar(u.id)}>Desativar</button>
              {/if}
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
h2 { font-size: 20px; color: var(--text); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--muted); border-bottom: 1px solid var(--border); font-weight: 500; }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
tr.inativo td { opacity: .5; }
.actions-cell { display: flex; gap: 8px; }
.empresas-cell { color: var(--muted); font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.badge.ativo { background: #1a4731; color: #3fb950; }
.role-admin { background: #1c2d4a; color: #58a6ff; }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
</style>
```

- [ ] **Step 2: Criar `frontend/src/routes/configuracoes/usuarios/novo/+page.svelte`**

```svelte
<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let nome     = '';
  let email    = '';
  let senha    = '';
  let role     = 'viewer';
  let empresasDisponiveis = [];
  let empresasSelecionadas = new Set();
  let salvando = false;
  let erro     = '';

  onMount(async () => {
    try {
      const lista = await api.listarEmpresas();
      empresasDisponiveis = lista.filter(e => e.ativo);
    } catch {
      erro = 'Erro ao carregar empresas.';
    }
  });

  function toggleEmpresa(id) {
    if (empresasSelecionadas.has(id)) empresasSelecionadas.delete(id);
    else empresasSelecionadas.add(id);
    empresasSelecionadas = new Set(empresasSelecionadas);
  }

  async function salvar() {
    erro = '';
    salvando = true;
    try {
      const u = await api.criarUsuario({ nome, email, senha, role });
      if (empresasSelecionadas.size > 0) {
        await api.vincularEmpresas(u.id, [...empresasSelecionadas]);
      }
      goto('/configuracoes/usuarios');
    } catch (e) {
      erro = e.message || 'Erro ao salvar usuário.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Novo Usuário — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Novo Usuário</h2>
    <a href="/configuracoes/usuarios" class="btn-ghost">Cancelar</a>
  </div>

  <div class="form card">
    <label>Nome completo <input bind:value={nome} /></label>
    <label>E-mail <input type="email" bind:value={email} /></label>
    <label>Senha <input type="password" bind:value={senha} /></label>
    <label>
      Perfil
      <select bind:value={role}>
        <option value="viewer">Visualizador</option>
        <option value="admin">Admin</option>
      </select>
    </label>

    <fieldset>
      <legend>Empresas com acesso</legend>
      {#each empresasDisponiveis as empresa}
        <label class="checkbox-label">
          <input
            type="checkbox"
            checked={empresasSelecionadas.has(empresa.id)}
            on:change={() => toggleEmpresa(empresa.id)}
          />
          {empresa.nome}
        </label>
      {/each}
    </fieldset>

    {#if erro}<p class="error">{erro}</p>{/if}

    <div class="actions">
      <a href="/configuracoes/usuarios" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" on:click={salvar} disabled={salvando || !nome || !email || !senha}>
        {salvando ? 'Salvando...' : 'Salvar Usuário'}
      </button>
    </div>
  </div>
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); }
.form { max-width: 480px; display: flex; flex-direction: column; gap: 16px; padding: 24px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; }
legend { font-size: 13px; color: var(--muted); padding: 0 4px; }
.checkbox-label { flex-direction: row; align-items: center; gap: 8px; cursor: pointer; color: var(--text); }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

- [ ] **Step 3: Criar `frontend/src/routes/configuracoes/usuarios/[id]/+page.svelte`**

```svelte
<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let usuario = null;
  let empresasDisponiveis = [];
  let empresasSelecionadas = new Set();
  let salvando = false;
  let erro     = '';

  onMount(async () => {
    try {
      const id = Number($page.params.id);
      const [u, todas, vinculadas] = await Promise.all([
        api.listarUsuarios().then(lista => lista.find(u => u.id === id)),
        api.listarEmpresas(),
        api.listarEmpresasUsuario(id)
      ]);
      if (!u) { goto('/configuracoes/usuarios'); return; }
      usuario = u;
      usuario.senha = '';
      empresasDisponiveis = todas.filter(e => e.ativo);
      empresasSelecionadas = new Set(vinculadas.map(e => e.id));
    } catch {
      goto('/configuracoes/usuarios');
    }
  });

  function toggleEmpresa(id) {
    if (empresasSelecionadas.has(id)) empresasSelecionadas.delete(id);
    else empresasSelecionadas.add(id);
    empresasSelecionadas = new Set(empresasSelecionadas);
  }

  async function salvar() {
    erro = '';
    salvando = true;
    try {
      await api.atualizarUsuario(usuario.id, {
        nome: usuario.nome, email: usuario.email,
        senha: usuario.senha || 'UNCHANGED',
        role: usuario.role, ativo: usuario.ativo
      });
      await api.vincularEmpresas(usuario.id, [...empresasSelecionadas]);
      goto('/configuracoes/usuarios');
    } catch (e) {
      erro = e.message || 'Erro ao salvar.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Editar Usuário — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Editar Usuário</h2>
    <a href="/configuracoes/usuarios" class="btn-ghost">Cancelar</a>
  </div>

  {#if usuario}
    <div class="form card">
      <label>Nome completo <input bind:value={usuario.nome} /></label>
      <label>E-mail <input type="email" bind:value={usuario.email} /></label>
      <label>
        Nova senha (deixe em branco para manter)
        <input type="password" bind:value={usuario.senha} placeholder="••••••••" />
      </label>
      <label>
        Perfil
        <select bind:value={usuario.role}>
          <option value="viewer">Visualizador</option>
          <option value="admin">Admin</option>
        </select>
      </label>

      <fieldset>
        <legend>Empresas com acesso</legend>
        {#each empresasDisponiveis as empresa}
          <label class="checkbox-label">
            <input
              type="checkbox"
              checked={empresasSelecionadas.has(empresa.id)}
              on:change={() => toggleEmpresa(empresa.id)}
            />
            {empresa.nome}
          </label>
        {/each}
      </fieldset>

      {#if erro}<p class="error">{erro}</p>{/if}

      <div class="actions">
        <a href="/configuracoes/usuarios" class="btn-ghost">Cancelar</a>
        <button class="btn-primary" on:click={salvar} disabled={salvando}>
          {salvando ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </div>
    </div>
  {:else}
    <p class="muted">Carregando...</p>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); }
.form { max-width: 480px; display: flex; flex-direction: column; gap: 16px; padding: 24px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; }
legend { font-size: 13px; color: var(--muted); padding: 0 4px; }
.checkbox-label { flex-direction: row; align-items: center; gap: 8px; cursor: pointer; color: var(--text); }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.error { color: var(--danger, #f85149); font-size: 13px; }
.muted { color: var(--muted); }
</style>
```

> **Nota sobre senha no PATCH:** O endpoint `PATCH /api/usuarios/{id}` sempre faz bcrypt do campo `senha`. Para edição sem alterar senha, é necessário enviar a senha atual ou tratar no backend. A solução limpa seria tornar `senha` opcional no PATCH — mas como o spec não menciona isso, o frontend envia `'UNCHANGED'` se o campo estiver vazio. O backend precisa de um ajuste mínimo: se `senha == 'UNCHANGED'`, não regravar o hash. Adicione esta verificação em `usuarios.py`:
>
> ```python
> @router.patch("/{id}")
> async def atualizar_usuario(id: int, body: UsuarioInput, user=Depends(require_admin)):
>     rows = await query_meta("SELECT * FROM usuarios WHERE id = $1", id)
>     if not rows:
>         raise HTTPException(status_code=404, detail="Usuário não encontrado")
>     
>     if body.senha == 'UNCHANGED':
>         senha_hash = dict(rows[0])["senha_hash"]  # keep existing hash
>     else:
>         senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()
>     
>     try:
>         rows = await query_meta("""
>             UPDATE usuarios
>             SET nome=$1, email=$2, senha_hash=$3, role=$4, ativo=$5
>             WHERE id=$6
>             RETURNING id, nome, email, role, ativo
>         """, body.nome, body.email, senha_hash, body.role, body.ativo, id)
>         return dict(rows[0])
>     except asyncpg.UniqueViolationError:
>         raise HTTPException(status_code=409, detail="Email já está em uso")
> ```

- [ ] **Step 4: Atualizar `backend/routes/usuarios.py` — PATCH com senha opcional**

Substituir o método `atualizar_usuario` por:

```python
@router.patch("/{id}")
async def atualizar_usuario(id: int, body: UsuarioInput, user=Depends(require_admin)):
    rows = await query_meta("SELECT * FROM usuarios WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if body.senha == 'UNCHANGED':
        senha_hash = dict(rows[0])["senha_hash"]
    else:
        senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt()).decode()

    try:
        rows = await query_meta("""
            UPDATE usuarios
            SET nome=$1, email=$2, senha_hash=$3, role=$4, ativo=$5
            WHERE id=$6
            RETURNING id, nome, email, role, ativo
        """, body.nome, body.email, senha_hash, body.role, body.ativo, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email já está em uso")
```

- [ ] **Step 5: Testar no browser**

1. Acessar http://localhost:3000/configuracoes/usuarios (como admin)
2. Verificar tabela com usuário admin e suas empresas
3. Clicar "+ Novo Usuário" → criar `viewer@datahub.local` / `viewer123` com acesso a alpha
4. Verificar que novo usuário aparece na tabela
5. Logar com `viewer@datahub.local` / `viewer123` → deve ver só empresa Alpha

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/configuracoes/usuarios/ backend/routes/usuarios.py
git commit -m "feat: add configuracoes/usuarios pages and fix PATCH senha optional"
```

---

## Checklist Final

Antes de considerar concluído, verificar todos os itens do PROMPT-EMPRESAS.md:

- [ ] Login com e-mail e senha funciona (sem campo empresa)
- [ ] Login com credenciais erradas mostra "E-mail ou senha inválidos."
- [ ] Após login aparece APENAS as empresas do usuário na tela de seleção
- [ ] Usuário com 1 empresa vai direto para o dashboard (auto-select)
- [ ] JWT é gerado APÓS selecionar a empresa
- [ ] Dashboard mostra nome da empresa no topbar
- [ ] Botão "Trocar empresa" redireciona para `/selecionar-empresa`
- [ ] Logout limpa tudo e volta para `/login`
- [ ] Admin vê seção "Admin" no menu lateral
- [ ] Viewer NÃO vê seção Admin
- [ ] Cadastro de empresa testa conexão antes de habilitar "Salvar"
- [ ] Upload de logo funciona e aparece no card da empresa
- [ ] Cadastro de usuário com vínculo de empresas funciona
- [ ] Usuário recém cadastrado consegue logar
