# SSO de painel para app externo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que um app externo (com seu próprio cadastro de usuários) abra um painel específico do DataHub direto pro navegador do usuário final, sem passar por `/login`, autenticando server-to-server com uma API key por empresa e validando o acesso contra uma view no banco da própria empresa.

**Architecture:** Dois endpoints novos em `/api/auth` (`sso-painel` e `sso/trocar`) implementam um fluxo de dois saltos — API key da empresa → token de troca de uso único (Redis) → JWT final com `tipo: "externo"`. O `middleware/auth.py` passa a emitir um "usuário" sintético pra esse tipo de token (sem linha em `usuarios`), e `routes/paineis.py` ganha uma trava de escopo (o token só abre o painel pro qual foi emitido) mais a injeção automática do `codigo_usuario` como parâmetro de query. No frontend, uma rota nova (`/sso`) troca o token e cai direto no painel, reaproveitando a UI existente.

**Tech Stack:** FastAPI, asyncpg, bcrypt, python-jose (JWT), Redis (aioredis), SvelteKit — mesmas libs já usadas no projeto, nenhuma dependência nova.

## Global Constraints

- Mensagens de erro de autenticação (`sso-painel`) usam texto genérico o suficiente pra não permitir enumeração (não dá pra saber de fora se falhou por empresa errada, api_key errada, ou sem acesso).
- Nenhuma mudança em `/login`, `/selecionar-empresa`, nem no fluxo de JWT/token existente para usuários internos — o novo `tipo: "externo"` é aditivo.
- Segredos (API key da empresa) só existem em texto puro no momento da geração; persistidos só como hash bcrypt.
- Contrato fixo esperado no banco de cada empresa que habilitar SSO: uma view chamada **`vw_datahub_sso_acesso`** com colunas `codigo_usuario` (text) e `painel_slug` (text) — uma linha por combinação liberada. O DataHub consulta com `EXISTS (SELECT 1 FROM vw_datahub_sso_acesso WHERE codigo_usuario = $1 AND painel_slug = $2)`. Esse nome/contrato precisa ser comunicado pro time do app externo antes de habilitar SSO numa empresa real.

---

### Task 1: Coluna `sso_api_key_hash` + endpoint admin de geração de API key por empresa

**Files:**
- Modify: `scripts/init-db.sql` (CREATE TABLE `empresas`, linha ~22-27)
- Modify: `scripts/init-meta-prod.sql` (CREATE TABLE `empresas`, linha ~16-27)
- Modify: `backend/routes/empresas.py`
- Test: `backend/tests/test_empresas_sso_api_key.py`

**Interfaces:**
- Produces: coluna `empresas.sso_api_key_hash VARCHAR(255)` (nullable); endpoint `POST /api/empresas/{id}/sso-api-key` → `{"api_key": "<texto-puro-uma-vez>"}`

- [ ] **Step 1: Aplicar a coluna no Postgres de dev**

Run:
```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS sso_api_key_hash VARCHAR(255);"
```
Expected: `ALTER TABLE`

- [ ] **Step 2: Refletir a coluna nos scripts de schema**

Em `scripts/init-db.sql`, dentro do `CREATE TABLE empresas (...)`, adicionar a coluna logo depois de `criado_em`:

```sql
CREATE TABLE empresas (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(50) UNIQUE NOT NULL,
    nome         VARCHAR(100) NOT NULL,
    db_host      VARCHAR(100) NOT NULL,
    db_port      INTEGER DEFAULT 5432,
    db_name      VARCHAR(100) NOT NULL,
    db_user      VARCHAR(100) NOT NULL,
    db_pass      VARCHAR(100) NOT NULL,
    ativo        BOOLEAN DEFAULT true,
    criado_em    TIMESTAMP DEFAULT NOW(),
    sso_api_key_hash VARCHAR(255)
);
```

Fazer a mesma adição em `scripts/init-meta-prod.sql` no `CREATE TABLE empresas`.

- [ ] **Step 3: Escrever o teste que falha**

Criar `backend/tests/test_empresas_sso_api_key.py`:

```python
def test_gerar_sso_api_key_retorna_texto_puro_uma_vez(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        f"/api/empresas/{alpha['id']}/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "api_key" in body
    assert len(body["api_key"]) > 20


def test_gerar_sso_api_key_empresa_inexistente_retorna_404(client, auth_token):
    res = client.post(
        "/api/empresas/999999/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 404


def test_gerar_sso_api_key_sem_autenticacao_retorna_403(client):
    res = client.post("/api/empresas/1/sso-api-key")
    assert res.status_code == 403
```

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_sso_api_key.py -v`
Expected: FAIL (`404 Not Found` — a rota ainda não existe)

- [ ] **Step 4: Implementar o endpoint**

Em `backend/routes/empresas.py`, adicionar os imports no topo:

```python
import bcrypt
import secrets
```

E o endpoint (colocar logo depois de `reativar_empresa`, antes de `upload_logo`):

```python
@router.post("/{id}/sso-api-key")
async def gerar_sso_api_key(id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    api_key = secrets.token_urlsafe(32)
    api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()

    await query_meta(
        "UPDATE empresas SET sso_api_key_hash = $1 WHERE id = $2",
        api_key_hash, id
    )
    return {"api_key": api_key}
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_sso_api_key.py -v`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql backend/routes/empresas.py backend/tests/test_empresas_sso_api_key.py
git commit -m "feat: add per-empresa SSO API key generation endpoint"
```

---

### Task 2: `POST /api/auth/sso-painel` — troca API key + código de usuário por token de troca

**Files:**
- Modify: `backend/routes/auth.py`
- Test: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Consumes: `empresas.sso_api_key_hash` (Task 1); contrato de view `vw_datahub_sso_acesso(codigo_usuario, painel_slug)` (ver Global Constraints)
- Produces: `POST /api/auth/sso-painel` → `{"redirect_url": "<FRONTEND_URL>/sso?exchange=<token>"}`; chave Redis `sso_exchange:<token>` (TTL 60s) contendo JSON `{"empresa_id", "company_slug", "codigo_usuario", "painel_slug"}` — consumida por Task 3.

- [ ] **Step 1: Escrever o teste que falha (fixture de ambiente + casos de erro)**

Criar `backend/tests/test_auth_sso_painel.py`:

```python
import asyncio
import uuid
import asyncpg
import pytest

VIEW_NAME = "vw_datahub_sso_acesso"


def _run(coro):
    return asyncio.run(coro)


async def _conn_alpha_admin():
    return await asyncpg.connect(
        host="postgres", port=5432, database="alpha_db",
        user="postgres", password="postgres123",
    )


def _criar_view_acesso(codigo_usuario, painel_slug):
    async def _go():
        conn = await _conn_alpha_admin()
        try:
            await conn.execute(f"""
                CREATE OR REPLACE VIEW {VIEW_NAME} AS
                SELECT '{codigo_usuario}'::text AS codigo_usuario,
                       '{painel_slug}'::text AS painel_slug
            """)
        finally:
            await conn.close()
    _run(_go())


def _dropar_view_acesso():
    async def _go():
        conn = await _conn_alpha_admin()
        try:
            await conn.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
        finally:
            await conn.close()
    _run(_go())


@pytest.fixture
def sso_ambiente(client, auth_token):
    """Cria empresa (alpha) com SSO habilitado + view de acesso liberando
    um codigo_usuario/painel_slug específicos. Devolve os dados pra cada teste
    montar seu próprio cenário, e limpa a view no final."""
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    api_key_res = client.post(
        f"/api/empresas/{alpha['id']}/sso-api-key",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert api_key_res.status_code == 200
    api_key = api_key_res.json()["api_key"]

    sufixo = uuid.uuid4().hex[:8]
    codigo_usuario = f"user_{sufixo}"
    painel_slug = f"painel_sso_teste_{sufixo}"

    _criar_view_acesso(codigo_usuario, painel_slug)

    painel_res = client.post(
        "/api/paineis/",
        json={"slug": painel_slug, "nome": "Painel SSO Teste", "empresa_id": alpha["id"]},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert painel_res.status_code == 200
    painel_id = painel_res.json()["id"]

    yield {
        "empresa_slug": "alpha",
        "empresa_id": alpha["id"],
        "api_key": api_key,
        "codigo_usuario": codigo_usuario,
        "painel_slug": painel_slug,
        "painel_id": painel_id,
    }

    _dropar_view_acesso()
    client.delete(f"/api/paineis/{painel_id}", headers={"Authorization": f"Bearer {auth_token}"})


def test_sso_painel_sucesso_devolve_redirect_url_com_exchange(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 200
    redirect_url = res.json()["redirect_url"]
    assert "/sso?exchange=" in redirect_url


def test_sso_painel_api_key_errada_retorna_401(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": "chave-errada-completamente",
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 401


def test_sso_painel_empresa_inexistente_retorna_401(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": "empresa-que-nao-existe",
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 401


def test_sso_painel_slug_de_outra_empresa_retorna_404(client, sso_ambiente, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    beta = next(e for e in empresas if e["slug"] == "beta")

    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": f"painel-que-so-existe-em-beta-{beta['id']}",
        },
    )
    assert res.status_code == 404


def test_sso_painel_sem_acesso_na_view_retorna_403(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": "codigo-sem-permissao-nenhuma",
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    assert res.status_code == 403
```

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: FAIL (`404 Not Found` em todos — a rota `/api/auth/sso-painel` ainda não existe)

- [ ] **Step 2: Implementar o endpoint**

Em `backend/routes/auth.py`, ajustar os imports do topo (adicionar `query_company` e `json`):

```python
import logging
import secrets
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from config.settings import settings
from config.databases import query_meta, query_company
from config.redis import get_redis
from middleware.auth import get_current_user
```

Adicionar o model de entrada (perto de `SelecionarEmpresaInput`):

```python
class SsoPainelInput(BaseModel):
    empresa_slug: str
    api_key: str
    codigo_usuario: str
    painel_slug: str
```

Adicionar o endpoint (logo depois de `selecionar_empresa`):

```python
@router.post("/sso-painel")
async def sso_painel(body: SsoPainelInput):
    try:
        empresa_rows = await query_meta(
            "SELECT id, slug, sso_api_key_hash FROM empresas WHERE slug = $1 AND ativo = true",
            body.empresa_slug
        )
        if not empresa_rows:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        empresa = dict(empresa_rows[0])

        if not empresa["sso_api_key_hash"]:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        if not bcrypt.checkpw(body.api_key.encode(), empresa["sso_api_key_hash"].encode()):
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        painel_rows = await query_meta(
            "SELECT id, slug FROM paineis WHERE slug = $1 AND empresa_id = $2 AND ativo = true",
            body.painel_slug, empresa["id"]
        )
        if not painel_rows:
            raise HTTPException(status_code=404, detail="Painel não encontrado")

        try:
            acesso_rows = await query_company(
                empresa["slug"],
                """
                SELECT EXISTS (
                    SELECT 1 FROM vw_datahub_sso_acesso
                    WHERE codigo_usuario = $1 AND painel_slug = $2
                ) AS tem_acesso
                """,
                body.codigo_usuario, body.painel_slug
            )
        except Exception as e:
            logger.error(f"Erro ao verificar acesso SSO: {e}")
            raise HTTPException(status_code=500, detail="Erro interno no servidor")

        if not acesso_rows[0]["tem_acesso"]:
            raise HTTPException(status_code=403, detail="Sem acesso a este painel")

        exchange_token = secrets.token_hex(32)
        redis = await get_redis()
        payload = json.dumps({
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "codigo_usuario": body.codigo_usuario,
            "painel_slug": body.painel_slug,
        })
        await redis.setex(f"sso_exchange:{exchange_token}", 60, payload)

        return {"redirect_url": f"{settings.FRONTEND_URL}/sso?exchange={exchange_token}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no sso-painel: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")
```

- [ ] **Step 3: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/auth.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: add POST /api/auth/sso-painel for external-app SSO handshake"
```

---

### Task 3: `POST /api/auth/sso/trocar` — troca o token de troca pelo JWT final

**Files:**
- Modify: `backend/routes/auth.py`
- Modify: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Consumes: chave Redis `sso_exchange:<token>` (Task 2)
- Produces: `POST /api/auth/sso/trocar` → `{"token": "<jwt>", "token_type": "bearer", "painel_slug": "..."}`. JWT contém `{"tipo": "externo", "empresa_id", "company_slug", "codigo_usuario", "painel_slug", "jti", "exp"}` — consumido por Task 4 (`middleware/auth.py`).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar em `backend/tests/test_auth_sso_painel.py`:

```python
def test_sso_trocar_token_valido_emite_jwt_externo(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]

    res = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert res.status_code == 200
    body = res.json()
    assert body["painel_slug"] == sso_ambiente["painel_slug"]
    assert len(body["token"]) > 20


def test_sso_trocar_token_ja_usado_retorna_401(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]

    primeira = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert primeira.status_code == 200

    segunda = client.post("/api/auth/sso/trocar", json={"exchange": exchange})
    assert segunda.status_code == 401


def test_sso_trocar_token_invalido_retorna_401(client):
    res = client.post("/api/auth/sso/trocar", json={"exchange": "token-que-nunca-existiu"})
    assert res.status_code == 401
```

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v -k sso_trocar`
Expected: FAIL (`404 Not Found` — a rota `/api/auth/sso/trocar` ainda não existe)

- [ ] **Step 2: Implementar o endpoint**

Em `backend/routes/auth.py`, adicionar `import uuid` no topo (junto com `import json`), o model de entrada:

```python
class SsoTrocarInput(BaseModel):
    exchange: str
```

E o endpoint (logo depois de `sso_painel`):

```python
@router.post("/sso/trocar")
async def sso_trocar(body: SsoTrocarInput):
    try:
        redis = await get_redis()
        raw = await redis.getdel(f"sso_exchange:{body.exchange}")
        if not raw:
            raise HTTPException(status_code=401, detail="Link inválido ou expirado")

        dados = json.loads(raw)
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        token = jwt.encode(
            {
                "tipo": "externo",
                "empresa_id": dados["empresa_id"],
                "company_slug": dados["company_slug"],
                "codigo_usuario": dados["codigo_usuario"],
                "painel_slug": dados["painel_slug"],
                "jti": str(uuid.uuid4()),
                "exp": expire,
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )
        return {"token": token, "token_type": "bearer", "painel_slug": dados["painel_slug"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao trocar token SSO: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")
```

- [ ] **Step 3: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: `8 passed`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/auth.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: add POST /api/auth/sso/trocar to redeem the one-time SSO exchange token"
```

---

### Task 4: `middleware/auth.py` — reconhecer tokens `tipo: "externo"`

**Files:**
- Modify: `backend/middleware/auth.py`
- Modify: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Consumes: JWT com `tipo: "externo"` (Task 3)
- Produces: `get_current_user(...)` devolve, pra token externo, o dict
  `{"id": None, "nome": None, "role": "externo", "tema": None, "empresa_id", "company_slug", "company_name", "codigo_usuario", "painel_slug"}` — consumido por Task 5 (`routes/paineis.py`) e por qualquer rota que já dependa de `get_current_user`.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar em `backend/tests/test_auth_sso_painel.py`:

```python
def _token_externo(client, sso_ambiente):
    handshake = client.post(
        "/api/auth/sso-painel",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
            "painel_slug": sso_ambiente["painel_slug"],
        },
    )
    exchange = handshake.json()["redirect_url"].split("exchange=")[1]
    return client.post("/api/auth/sso/trocar", json={"exchange": exchange}).json()["token"]


def test_me_com_token_externo_devolve_empresa_real_e_codigo_usuario(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "externo"
    assert body["id"] is None
    assert body["company_slug"] == "alpha"
    assert body["company_name"] == "Empresa Alpha Ltda"
    assert body["codigo_usuario"] == sso_ambiente["codigo_usuario"]
    assert body["painel_slug"] == sso_ambiente["painel_slug"]
```

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v -k me_com_token_externo`
Expected: FAIL (`403 Acesso negado` — `get_current_user` ainda tenta achar `user_id` em `usuarios` e não encontra)

- [ ] **Step 2: Implementar a ramificação no middleware**

Substituir o corpo de `get_current_user` em `backend/middleware/auth.py`:

```python
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
    if empresa_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    redis = await get_redis()

    if payload.get("tipo") == "externo":
        jti = payload.get("jti")
        codigo_usuario = payload.get("codigo_usuario")
        painel_slug = payload.get("painel_slug")
        if not jti or not codigo_usuario or not painel_slug:
            raise HTTPException(status_code=401, detail="Token inválido")

        if await redis.get(f"blacklist:externo:{jti}"):
            raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

        empresa_rows = await query_meta(
            "SELECT id, nome, slug FROM empresas WHERE id = $1 AND ativo = true",
            empresa_id
        )
        if not empresa_rows:
            raise HTTPException(status_code=403, detail="Acesso negado")
        empresa = dict(empresa_rows[0])

        return {
            "id": None,
            "nome": None,
            "role": "externo",
            "tema": None,
            "empresa_id": empresa["id"],
            "company_slug": empresa["slug"],
            "company_name": empresa["nome"],
            "codigo_usuario": codigo_usuario,
            "painel_slug": painel_slug,
        }

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    if await redis.get(f"blacklist:{user_id}"):
        raise HTTPException(status_code=401, detail="Token inválido ou sessão encerrada")

    rows = await query_meta("""
        SELECT u.id, u.nome, u.role, u.tema,
               e.id AS empresa_id, e.slug AS company_slug, e.nome AS company_name
        FROM usuarios u
        JOIN usuario_empresas ue ON ue.usuario_id = u.id
        JOIN empresas e ON e.id = ue.empresa_id
        WHERE u.id = $1 AND e.id = $2 AND u.ativo = true AND e.ativo = true
    """, user_id, empresa_id)

    if not rows:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return dict(rows[0])
```

(`require_admin` não muda — `role != "admin"` já bloqueia tokens externos automaticamente.)

- [ ] **Step 3: Rodar o teste e confirmar que passa**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: `9 passed`

- [ ] **Step 4: Rodar a suíte inteira pra garantir que o fluxo interno não quebrou**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos os testes existentes continuam passando (nenhuma regressão no login/JWT interno)

- [ ] **Step 5: Commit**

```bash
git add backend/middleware/auth.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: recognize tipo=externo JWTs in get_current_user middleware"
```

---

### Task 5: `routes/paineis.py` — travar o painel pro escopo do token e injetar `codigo_usuario_externo`

**Files:**
- Modify: `backend/routes/paineis.py`
- Modify: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Consumes: `user["role"] == "externo"`, `user["painel_slug"]`, `user["codigo_usuario"]` (Task 4)
- Produces: `buscar_painel_por_slug` e `renderizar_painel` retornam 403 se o token externo pedir um painel diferente do que foi emitido; `renderizar_painel` sempre injeta `filtros["codigo_usuario_externo"] = user["codigo_usuario"]`, sobrescrevendo qualquer valor vindo da query string.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar em `backend/tests/test_auth_sso_painel.py` (a fixture `sso_ambiente` já cria painel+empresa; falta uma query/indicador pra testar a injeção do filtro):

```python
def test_buscar_painel_por_slug_com_token_externo_de_outro_painel_retorna_403(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        "/api/paineis/slug/painel-que-nao-foi-autorizado",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_buscar_painel_por_slug_com_token_externo_do_proprio_painel_funciona(client, sso_ambiente):
    token = _token_externo(client, sso_ambiente)

    res = client.get(
        f"/api/paineis/slug/{sso_ambiente['painel_slug']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["id"] == sso_ambiente["painel_id"]


def test_renderizar_painel_injeta_codigo_usuario_do_token_ignorando_query_string(
    client, sso_ambiente, auth_token
):
    query_slug = f"query_sso_teste_{uuid.uuid4().hex[:8]}"
    query_res = client.post(
        "/api/queries/",
        json={
            "slug": query_slug,
            "nome": "Query SSO Teste",
            "sql_texto": "SELECT $1::text AS valor, 'codigo' AS label",
            "tipo": "kpi",
            "empresa_id": sso_ambiente["empresa_id"],
            "cache_ttl": 0,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert query_res.status_code == 200
    query_id = query_res.json()["id"]

    param_res = client.put(
        f"/api/queries/{query_id}/parametros",
        json=[{"nome": "codigo_usuario_externo", "tipo": "text", "obrigatorio": False}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert param_res.status_code == 200

    ind_res = client.put(
        f"/api/paineis/{sso_ambiente['painel_id']}/indicadores",
        json=[{"query_slug": query_slug, "linha": 1, "coluna": 1}],
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ind_res.status_code == 200

    token = _token_externo(client, sso_ambiente)
    res = client.get(
        f"/api/paineis/{sso_ambiente['painel_id']}/renderizar?codigo_usuario_externo=valor-forjado-pelo-cliente",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    dados = res.json()["indicadores"][0]["dados"]
    assert dados[0]["valor"] == sso_ambiente["codigo_usuario"]

    client.delete(f"/api/queries/{query_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v -k "buscar_painel_por_slug_com_token_externo or renderizar_painel_injeta"`
Expected: FAIL — `buscar_painel_por_slug` devolve 404 em vez de 403 (a query hoje exige `painel_usuarios`, que não existe pra token externo, então nunca acha linha nenhuma — nem pro painel certo, nem pro errado); e o teste de injeção falha porque `dados[0]["valor"]` vem `"valor-forjado-pelo-cliente"` em vez do código real.

- [ ] **Step 2: Implementar a trava de escopo e a injeção do filtro**

Em `backend/routes/paineis.py`, substituir `buscar_painel_por_slug`:

```python
@router.get("/slug/{slug}")
async def buscar_painel_por_slug(slug: str, user=Depends(get_current_user)):
    if user["role"] == "externo":
        if user["painel_slug"] != slug:
            raise HTTPException(403, "Sem acesso a este painel")
        rows = await query_meta("""
            SELECT * FROM paineis
            WHERE slug = $1 AND empresa_id = $2 AND ativo = true
        """, slug, user["empresa_id"])
        if not rows:
            raise HTTPException(404, "Painel não encontrado")
        return dict(rows[0])

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
```

E em `renderizar_painel`, adicionar a checagem de escopo logo após buscar o painel, e a injeção do filtro logo após montar `filtros`:

```python
@router.get("/{painel_id}/renderizar")
async def renderizar_painel(
    painel_id: int,
    request: Request,
    user=Depends(get_current_user)
):
    """
    Executa todas as queries do painel com os filtros aplicados.
    Filtros chegam como query params: ?data_inicio=2026-01-01&data_fim=2026-06-30
    """
    from services.query_runner import resolver_query

    filtros = dict(request.query_params)

    painel_rows = await query_meta("SELECT * FROM paineis WHERE id = $1", painel_id)
    if not painel_rows:
        raise HTTPException(404, "Painel não encontrado")

    if user["role"] == "externo":
        if painel_rows[0]["slug"] != user["painel_slug"]:
            raise HTTPException(403, "Sem acesso a este painel")
        filtros["codigo_usuario_externo"] = user["codigo_usuario"]

    indicadores = await query_meta("""
        SELECT pi.*, q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
               q.chart_fonte_tamanho, q.chart_truncar_label, q.chart_truncar_tamanho, q.chart_mostrar_valor,
               q.chart_valor_label
        FROM painel_indicadores pi
        LEFT JOIN queries q ON q.slug = pi.query_slug AND q.ativo = true
        WHERE pi.painel_id = $1
        ORDER BY pi.linha, pi.coluna
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

- [ ] **Step 3: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: `12 passed`

- [ ] **Step 4: Rodar a suíte inteira**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos passam, nenhuma regressão no fluxo interno de painéis

- [ ] **Step 5: Commit**

```bash
git add backend/routes/paineis.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: scope external SSO tokens to a single painel and inject codigo_usuario filter"
```

---

### Task 6: Frontend — rota `/sso`, `api.ssoTrocar` e `PUBLIC_ROUTES`

**Files:**
- Modify: `frontend/src/lib/api.js`
- Create: `frontend/src/routes/sso/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte:9`

**Interfaces:**
- Consumes: `POST /api/auth/sso/trocar` (Task 3) → `{"token", "token_type", "painel_slug"}`
- Produces: `api.ssoTrocar(exchange)`; rota `/sso?exchange=...` que autentica e redireciona pra `/painel/{slug}`

- [ ] **Step 1: Adicionar `ssoTrocar` em `api.js`**

Em `frontend/src/lib/api.js`, logo abaixo de `logout: () => request('/api/auth/logout', { method: 'POST' }),`:

```js
    ssoTrocar: (exchange) =>
        request('/api/auth/sso/trocar', { method: 'POST', body: JSON.stringify({ exchange }) }),
```

- [ ] **Step 2: Adicionar `/sso` em `PUBLIC_ROUTES`**

Em `frontend/src/routes/+layout.svelte:9`, trocar:

```js
  const PUBLIC_ROUTES = ['/login', '/selecionar-empresa'];
```

por:

```js
  const PUBLIC_ROUTES = ['/login', '/selecionar-empresa', '/sso'];
```

Sem essa mudança, o guard de autenticação do layout (`onMount`/`beforeNavigate`, que roda em toda rota fora dessa lista) redireciona pra `/login` antes da troca de token no passo seguinte conseguir rodar.

- [ ] **Step 3: Criar a rota `/sso`**

Criar `frontend/src/routes/sso/+page.svelte`:

```svelte
<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { token } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';

  let erro = '';

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const exchange = params.get('exchange');
    if (!exchange) { erro = 'Link inválido.'; return; }

    try {
      const res = await api.ssoTrocar(exchange);
      token.set(res.token);
      goto(`/painel/${res.painel_slug}`);
    } catch {
      erro = 'Link inválido ou expirado.';
    }
  });
</script>

<svelte:head><title>Entrando... — DataHub</title></svelte:head>

<div class="wrap">
  {#if erro}
    <p class="error">{erro}</p>
  {:else}
    <p>Entrando...</p>
  {/if}
</div>

<style>
.wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  color: var(--text);
}
.error { color: var(--danger, #f85149); }
</style>
```

- [ ] **Step 4: Rebuild do container do frontend e verificação manual**

Run:
```bash
docker restart datahub_backend datahub_frontend
```

Gerar um cenário de teste ponta a ponta:
1. No backend, gerar uma API key pra `alpha` (via `POST /api/empresas/{id}/sso-api-key` autenticado como admin).
2. Criar uma view `vw_datahub_sso_acesso` no banco `alpha_db` liberando um `codigo_usuario`/`painel_slug` de um painel real já cadastrado em `alpha`.
3. Chamar `POST /api/auth/sso-painel` com esses dados (via `curl` ou Postman) e pegar o `redirect_url`.
4. Abrir esse `redirect_url` num navegador.

Expected: a página `/sso` aparece brevemente ("Entrando...") e redireciona pro painel, exibindo sidebar/topbar normalmente com o nome da empresa "Empresa Alpha Ltda" na topbar, sem passar por `/login`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/routes/sso/+page.svelte frontend/src/routes/+layout.svelte
git commit -m "feat: add /sso frontend route to redeem external-app SSO tokens"
```

---

## Pendência de deploy (documentar, não executar aqui)

- Aplicar `ALTER TABLE empresas ADD COLUMN sso_api_key_hash VARCHAR(255);` no Postgres de produção (VPS/EasyPanel) — mesma pendência manual já documentada em `docs/superpowers/specs/2026-07-13-sso-painel-externo-design.md` e no padrão de "schema drift" já conhecido no projeto.
- Comunicar o contrato da view `vw_datahub_sso_acesso(codigo_usuario, painel_slug)` pro time do app externo antes de habilitar SSO em qualquer empresa real (`prats`, `vitoria-agronegocios`).
