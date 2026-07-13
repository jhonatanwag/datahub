# Configuração de SSO por empresa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a chave de API só-por-curl e a query de acesso hardcoded (`vw_datahub_sso_acesso`) do feature de SSO externo por configuração de admin por empresa — uma query SQL editável que recebe só `codigo_usuario` e devolve a lista de `painel_slug` liberados, reaproveitada tanto pra abrir um painel específico quanto pra um novo endpoint de listagem usado em menus do app externo.

**Architecture:** Novo módulo `backend/services/sso.py` concentra a lógica compartilhada (validar api_key da empresa, rodar a query configurada, validar a coluna `painel_slug` do resultado) usada por três lugares: `sso_painel` (já existe, passa a checar a lista em vez de um `EXISTS` de 2 parâmetros), um novo `sso_meus_paineis` (lista painéis liberados), e um novo `testar_sso_acesso` (admin testa a query antes de salvar). O frontend ganha uma seção nova na tela de edição de empresa pra gerar a chave e editar/testar essa query.

**Tech Stack:** FastAPI, asyncpg, bcrypt, SvelteKit — mesmas libs já usadas, nenhuma dependência nova.

## Global Constraints

- SSO só fica "habilitado" pra uma empresa quando **as duas** colunas existem: `sso_api_key_hash` E `sso_query_acesso`. Faltando qualquer uma, `sso_painel`/`sso_meus_paineis` devolvem o mesmo `401 "Credenciais inválidas"` genérico já usado hoje (não distinguir motivo, evita enumeração).
- Contrato da query configurável: recebe **só `$1 = codigo_usuario`**, devolve N linhas com uma coluna chamada literalmente `painel_slug`. Validado com uma mensagem clara (nunca deixar erro cru de SQL vazar) — mesmo padrão de `_validar_colunas_valor_label` em `backend/routes/variaveis.py:43-53`.
- O endpoint de listagem (`sso-meus-paineis`) **não gera token nem `redirect_url`** — só metadados (`slug`, `nome`, `icone`) pra montar menu. Abrir de verdade continua sendo só via `sso-painel`.
- Nenhuma mudança em `/login`, `/selecionar-empresa`, no formato do JWT interno, ou no comportamento de `painel_usuarios`/rotas internas — tudo aditivo sobre o que já está em `master`.

---

### Task 1: Schema + módulo compartilhado + `sso_painel` no novo contrato

**Files:**
- Modify: `scripts/init-db.sql`
- Modify: `scripts/init-meta-prod.sql`
- Modify: `README.md`
- Modify: `backend/routes/empresas.py`
- Create: `backend/services/sso.py`
- Modify: `backend/routes/auth.py`
- Modify: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Produces: coluna `empresas.sso_query_acesso TEXT` (nullable); `backend/services/sso.py` exporta `validar_coluna_painel_slug(data: list) -> None`, `async def validar_empresa_sso(empresa_slug: str, api_key: str) -> dict` (devolve a linha de `empresas`, incluindo `sso_query_acesso`, ou levanta `HTTPException`), `async def buscar_slugs_liberados(empresa: dict, codigo_usuario: str) -> list[str]` — usados por Task 2 e Task 3.

- [ ] **Step 1: Aplicar a coluna no Postgres de dev**

Run:
```bash
docker exec datahub_postgres psql -U postgres -d datahub_meta -c "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS sso_query_acesso TEXT;"
```
Expected: `ALTER TABLE`

- [ ] **Step 2: Refletir a coluna nos scripts de schema e no README**

Em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`, no `CREATE TABLE empresas (...)`, adicionar a coluna logo depois de `sso_api_key_hash`:

```sql
    sso_api_key_hash VARCHAR(255),
    sso_query_acesso TEXT
);
```

Em `README.md`, na seção "Deltas de schema pendentes", adicionar ao bloco de `SELECT column_name` existente e ao bloco de `ALTER TABLE`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'empresas'
  AND column_name IN ('sso_api_key_hash', 'sso_query_acesso');
```

```sql
-- 2026-07-13 — query configurável de acesso SSO por empresa (codigo_usuario -> lista de painel_slug)
ALTER TABLE empresas ADD COLUMN sso_query_acesso TEXT;
```

- [ ] **Step 3: `PATCH /api/empresas/{id}` aceita `sso_query_acesso`; `GET /api/empresas/{id}` devolve o valor salvo**

Em `backend/routes/empresas.py`, adicionar o campo em `EmpresaUpdate`:

```python
class EmpresaUpdate(BaseModel):
    slug: str
    nome: str
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_pass: str | None = None  # None = keep existing
    ativo: bool = True
    sso_query_acesso: str | None = None
```

Atualizar `buscar_empresa` pra incluir a coluna no `SELECT` (não é segredo, ao contrário de `db_pass`/`sso_api_key_hash` — o admin precisa reler o que já salvou):

```python
@router.get("/{id}")
async def buscar_empresa(id: int, user=Depends(require_admin)):
    rows = await query_meta(
        "SELECT id, slug, nome, db_host, db_port, db_name, db_user, ativo, criado_em, sso_query_acesso FROM empresas WHERE id = $1",
        id
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    row = dict(rows[0])
    row["logo_url"] = f"/api/empresas/{id}/logo"
    return row
```

Atualizar `atualizar_empresa` pra persistir o campo:

```python
@router.patch("/{id}")
async def atualizar_empresa(id: int, body: EmpresaUpdate, user=Depends(require_admin)):
    rows = await query_meta("SELECT id FROM empresas WHERE id = $1", id)
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    try:
        rows = await query_meta("""
            UPDATE empresas
            SET slug=$1, nome=$2, db_host=$3, db_port=$4, db_name=$5,
                db_user=$6,
                db_pass=COALESCE($7, db_pass),
                ativo=$8,
                sso_query_acesso=$9
            WHERE id=$10
            RETURNING id, slug, nome, ativo
        """, body.slug, body.nome, body.db_host, body.db_port,
            body.db_name, body.db_user, body.db_pass, body.ativo,
            body.sso_query_acesso, id)
        return dict(rows[0])
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Slug já está em uso")
```

**Nota:** isso troca `sso_query_acesso=NULL` sempre que o PATCH for enviado sem o campo (Pydantic default `None`) — diferente de `db_pass`, que usa `COALESCE` pra não apagar o valor salvo quando o campo vem vazio. Isso é intencional aqui: o frontend (Task 4) sempre vai reenviar o valor atual da textarea (carregado no `onMount` a partir do `GET`), então não precisa do mesmo comportamento de "não sobrescrever" que a senha tem — mas documentar isso evita confusão futura se alguém copiar o padrão de `db_pass` sem pensar.

- [ ] **Step 4: Migrar a fixture de teste pro novo contrato (esperado falhar em seguida)**

Em `backend/tests/test_auth_sso_painel.py`, remover completamente os helpers antigos baseados em view real
(`VIEW_NAME`, `_run`, `_conn_alpha_admin`, `_criar_view_acesso`, `_dropar_view_acesso`) e os imports que só
existiam pra eles (`asyncio`, `asyncpg`) — o novo contrato não precisa mais criar/dropar objetos reais no
banco da empresa, porque a query em si pode ser auto-contida (`VALUES` inline). Substituir a fixture
`sso_ambiente` por:

```python
@pytest.fixture
def sso_ambiente(client, auth_token):
    """Cria empresa (alpha) com SSO habilitado (API key + sso_query_acesso)
    e um painel de teste. Devolve os dados pra cada teste montar seu
    próprio cenário."""
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

    # Query auto-contida (sem precisar de tabela/view real no banco da
    # empresa): libera só esse codigo_usuario pra esse painel_slug.
    sso_query_acesso = (
        f"SELECT painel_slug FROM (VALUES ('{codigo_usuario}', '{painel_slug}')) "
        f"AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1"
    )

    empresa_atual = client.get(
        f"/api/empresas/{alpha['id']}", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    patch_res = client.patch(
        f"/api/empresas/{alpha['id']}",
        json={
            "slug": empresa_atual["slug"],
            "nome": empresa_atual["nome"],
            "db_host": empresa_atual["db_host"],
            "db_port": empresa_atual["db_port"],
            "db_name": empresa_atual["db_name"],
            "db_user": empresa_atual["db_user"],
            "ativo": empresa_atual["ativo"],
            "sso_query_acesso": sso_query_acesso,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert patch_res.status_code == 200

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

    client.delete(f"/api/paineis/{painel_id}", headers={"Authorization": f"Bearer {auth_token}"})
```

Nenhum teste do arquivo precisa mudar de corpo — todos continuam chamando `sso_painel`/`sso/trocar`/rotas de
painel exatamente como antes, só a fixture muda. `uuid` e `pytest` continuam sendo os únicos imports
necessários no topo do arquivo (mais `datetime`/`jose.jwt`/`config.settings` que o teste de expiração já usa).

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: FAIL em quase todos os testes que dependem de `sso_painel` devolver acesso — o backend ainda
consulta a view fixa `vw_datahub_sso_acesso` (que não existe mais nesse banco), não a coluna
`sso_query_acesso` que a fixture acabou de salvar.

- [ ] **Step 5: Criar `backend/services/sso.py`**

```python
"""Funções compartilhadas do fluxo de SSO externo (routes/auth.py + routes/empresas.py)."""
import logging
import bcrypt
from typing import List
from fastapi import HTTPException
from config.databases import query_meta, query_company

logger = logging.getLogger("datahub")


def validar_coluna_painel_slug(data: List[dict]) -> None:
    """A query de acesso SSO precisa devolver uma coluna chamada exatamente
    'painel_slug' (o backend lê essa chave literalmente). Sem essa checagem,
    uma query com coluna de outro nome roda com sucesso e devolve linhas,
    mas nenhum painel nunca é liberado, silenciosamente."""
    if data and "painel_slug" not in data[0]:
        colunas = list(data[0].keys())
        raise ValueError(
            f"A query retornou as colunas {colunas}, mas era esperado 'painel_slug'. "
            f"Use um alias, ex: SELECT slug AS painel_slug FROM tabela WHERE codigo_usuario = $1"
        )


async def validar_empresa_sso(empresa_slug: str, api_key: str) -> dict:
    """Valida a API key de SSO de uma empresa e devolve a linha completa de
    `empresas` (incluindo sso_query_acesso) se válida. Levanta HTTPException
    401 genérico (mesma mensagem pra empresa inexistente, SSO não
    habilitado, ou chave errada — evita enumeração) caso contrário."""
    empresa_rows = await query_meta(
        "SELECT id, slug, sso_api_key_hash, sso_query_acesso FROM empresas WHERE slug = $1 AND ativo = true",
        empresa_slug
    )
    if not empresa_rows:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    empresa = dict(empresa_rows[0])

    if not empresa["sso_api_key_hash"] or not empresa["sso_query_acesso"]:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    if not bcrypt.checkpw(api_key.encode(), empresa["sso_api_key_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    return empresa


async def buscar_slugs_liberados(empresa: dict, codigo_usuario: str) -> List[str]:
    """Roda a query_acesso configurada da empresa (banco da própria empresa,
    via query_company) e devolve a lista de painel_slug liberados pro
    codigo_usuario informado."""
    try:
        rows = await query_company(empresa["slug"], empresa["sso_query_acesso"], codigo_usuario)
    except Exception as e:
        logger.error(f"Erro ao rodar sso_query_acesso da empresa {empresa['slug']}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")

    data = [dict(r) for r in rows]
    try:
        validar_coluna_painel_slug(data)
    except ValueError as e:
        logger.error(f"sso_query_acesso da empresa {empresa['slug']} com formato inválido: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")

    return [r["painel_slug"] for r in data]
```

- [ ] **Step 6: Refatorar `sso_painel` em `backend/routes/auth.py` pro novo contrato**

Trocar os imports do topo — remover o `bcrypt` do bloco de checagem de api_key (continua sendo usado em
`login`, então o `import bcrypt` no topo do arquivo permanece) e adicionar:

```python
from services.sso import validar_empresa_sso, buscar_slugs_liberados
```

Substituir o corpo de `sso_painel`:

```python
@router.post("/sso-painel")
async def sso_painel(body: SsoPainelInput):
    try:
        empresa = await validar_empresa_sso(body.empresa_slug, body.api_key)

        painel_rows = await query_meta(
            "SELECT id, slug FROM paineis WHERE slug = $1 AND empresa_id = $2 AND ativo = true",
            body.painel_slug, empresa["id"]
        )
        if not painel_rows:
            raise HTTPException(status_code=404, detail="Painel não encontrado")

        slugs_liberados = await buscar_slugs_liberados(empresa, body.codigo_usuario)
        if body.painel_slug not in slugs_liberados:
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

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: todos os testes do arquivo passam (mesma contagem de antes — só a fixture mudou de mecanismo, os
casos continuam os mesmos)

- [ ] **Step 8: Rodar a suíte inteira**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos passam, nenhuma regressão

- [ ] **Step 9: Commit**

```bash
git add scripts/init-db.sql scripts/init-meta-prod.sql README.md backend/routes/empresas.py backend/services/sso.py backend/routes/auth.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: make SSO access query configurable per empresa"
```

---

### Task 2: `POST /api/auth/sso-meus-paineis`

**Files:**
- Modify: `backend/routes/auth.py`
- Modify: `backend/tests/test_auth_sso_painel.py`

**Interfaces:**
- Consumes: `validar_empresa_sso`, `buscar_slugs_liberados` (Task 1)
- Produces: `POST /api/auth/sso-meus-paineis` → `[{"slug", "nome", "icone"}, ...]` (sem token, sem `redirect_url`)

- [ ] **Step 1: Escrever os testes que falham**

Adicionar em `backend/tests/test_auth_sso_painel.py`:

```python
def test_sso_meus_paineis_lista_paineis_liberados(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-meus-paineis",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": sso_ambiente["codigo_usuario"],
        },
    )
    assert res.status_code == 200
    slugs = [p["slug"] for p in res.json()]
    assert slugs == [sso_ambiente["painel_slug"]]
    assert "redirect_url" not in res.json()
    assert res.json()[0]["nome"] == "Painel SSO Teste"


def test_sso_meus_paineis_codigo_sem_acesso_devolve_lista_vazia(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-meus-paineis",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": sso_ambiente["api_key"],
            "codigo_usuario": "codigo-sem-permissao-nenhuma",
        },
    )
    assert res.status_code == 200
    assert res.json() == []


def test_sso_meus_paineis_api_key_errada_retorna_401(client, sso_ambiente):
    res = client.post(
        "/api/auth/sso-meus-paineis",
        json={
            "empresa_slug": sso_ambiente["empresa_slug"],
            "api_key": "chave-errada-completamente",
            "codigo_usuario": sso_ambiente["codigo_usuario"],
        },
    )
    assert res.status_code == 401
```

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v -k sso_meus_paineis`
Expected: FAIL (`404 Not Found` — a rota ainda não existe)

- [ ] **Step 2: Implementar o endpoint**

Em `backend/routes/auth.py`, adicionar o model de entrada (perto de `SsoPainelInput`):

```python
class SsoMeusPaineisInput(BaseModel):
    empresa_slug: str
    api_key: str
    codigo_usuario: str
```

E o endpoint (logo depois de `sso_painel`, antes de `sso_trocar`):

```python
@router.post("/sso-meus-paineis")
async def sso_meus_paineis(body: SsoMeusPaineisInput):
    try:
        empresa = await validar_empresa_sso(body.empresa_slug, body.api_key)
        slugs_liberados = await buscar_slugs_liberados(empresa, body.codigo_usuario)

        if not slugs_liberados:
            return []

        rows = await query_meta(
            "SELECT slug, nome, icone FROM paineis WHERE empresa_id = $1 AND slug = ANY($2::text[]) AND ativo = true",
            empresa["id"], slugs_liberados
        )
        return [dict(r) for r in rows]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no sso-meus-paineis: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")
```

- [ ] **Step 3: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_auth_sso_painel.py -v`
Expected: todos passam (os anteriores + os 3 novos)

- [ ] **Step 4: Commit**

```bash
git add backend/routes/auth.py backend/tests/test_auth_sso_painel.py
git commit -m "feat: add POST /api/auth/sso-meus-paineis to list accessible painéis"
```

---

### Task 3: `POST /api/empresas/testar-sso-acesso` (admin)

**Files:**
- Modify: `backend/routes/empresas.py`
- Modify: `backend/tests/test_empresas_sso_api_key.py`

**Interfaces:**
- Consumes: `validar_coluna_painel_slug` (Task 1)
- Produces: `POST /api/empresas/testar-sso-acesso` → `{"ok": true, "slugs": [...]}` ou `{"ok": false, "erro": "..."}`

- [ ] **Step 1: Escrever os testes que falham**

Adicionar em `backend/tests/test_empresas_sso_api_key.py`:

```python
def test_testar_sso_acesso_com_query_valida_devolve_slugs(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT painel_slug FROM (VALUES ('teste_a', 'painel_x'), ('teste_a', 'painel_y')) AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert sorted(body["slugs"]) == ["painel_x", "painel_y"]


def test_testar_sso_acesso_sem_coluna_painel_slug_retorna_erro_claro(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT 1 AS id, 'x' AS nome",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "painel_slug" in body["erro"]


def test_testar_sso_acesso_com_sql_invalido_retorna_erro_sem_500(client, auth_token):
    empresas = client.get(
        "/api/empresas/", headers={"Authorization": f"Bearer {auth_token}"}
    ).json()
    alpha = next(e for e in empresas if e["slug"] == "alpha")

    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": alpha["id"],
            "query": "SELECT * FROM tabela_que_nao_existe",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["erro"]


def test_testar_sso_acesso_empresa_invalida_retorna_erro_sem_500(client, auth_token):
    res = client.post(
        "/api/empresas/testar-sso-acesso",
        json={
            "empresa_id": 999999,
            "query": "SELECT painel_slug FROM (VALUES ('a', 'b')) AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1",
            "codigo_usuario": "teste_a",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
```

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_sso_api_key.py -v`
Expected: FAIL (`404 Not Found` — a rota `/api/empresas/testar-sso-acesso` ainda não existe)

- [ ] **Step 2: Implementar o endpoint**

Em `backend/routes/empresas.py`, ajustar o import de `config.databases` pra incluir `query_company`, e importar o validador:

```python
from config.databases import query_meta, query_company
from services.sso import validar_coluna_painel_slug
```

Adicionar o model de entrada:

```python
class TestarSsoAcessoInput(BaseModel):
    empresa_id: int
    query: str
    codigo_usuario: str
```

E o endpoint (logo depois de `gerar_sso_api_key`):

```python
@router.post("/testar-sso-acesso")
async def testar_sso_acesso(body: TestarSsoAcessoInput, user=Depends(require_admin)):
    emp = await query_meta(
        "SELECT slug FROM empresas WHERE id = $1 AND ativo = true", body.empresa_id
    )
    if not emp:
        return {"ok": False, "erro": f"Empresa #{body.empresa_id} não encontrada ou inativa"}

    try:
        rows = await query_company(emp[0]["slug"], body.query, body.codigo_usuario)
        data = [dict(r) for r in rows]
        validar_coluna_painel_slug(data)
        return {"ok": True, "slugs": [r["painel_slug"] for r in data]}
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
```

- [ ] **Step 3: Rodar os testes e confirmar que passam**

Run: `docker exec datahub_backend python -m pytest tests/test_empresas_sso_api_key.py -v`
Expected: todos passam (os 3 de antes + os 4 novos)

- [ ] **Step 4: Rodar a suíte inteira**

Run: `docker exec datahub_backend python -m pytest tests/ -v`
Expected: todos passam, nenhuma regressão

- [ ] **Step 5: Commit**

```bash
git add backend/routes/empresas.py backend/tests/test_empresas_sso_api_key.py
git commit -m "feat: add POST /api/empresas/testar-sso-acesso to validate the configured SSO query"
```

---

### Task 4: Frontend — seção "SSO Externo" na tela de edição de empresa

**Files:**
- Modify: `frontend/src/lib/api.js`
- Modify: `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`

**Interfaces:**
- Consumes: `POST /api/empresas/{id}/sso-api-key` (já existe), `POST /api/empresas/testar-sso-acesso` (Task 3), `PATCH /api/empresas/{id}` com `sso_query_acesso` (Task 1)

- [ ] **Step 1: Adicionar as duas funções novas em `api.js`**

Em `frontend/src/lib/api.js`, logo abaixo de `testarConexao:`:

```js
    gerarSsoApiKey: (id) => request(`/api/empresas/${id}/sso-api-key`, { method: 'POST' }),
    testarSsoAcesso: (data) => request('/api/empresas/testar-sso-acesso', { method: 'POST', body: JSON.stringify(data) }),
```

- [ ] **Step 2: Adicionar a seção "SSO Externo" na tela de edição**

Em `frontend/src/routes/configuracoes/empresas/[id]/+page.svelte`, adicionar ao `<script>` (perto das outras
variáveis de estado):

```js
  let ssoApiKeyGerada = null;   // texto puro, só existe em memória após gerar
  let ssoGerando = false;
  let ssoTesteCodigoUsuario = '';
  let ssoTesteStatus = null;    // null | 'ok' | 'fail'
  let ssoTesteResultado = '';
  let ssoTestando = false;
```

E as funções (perto de `testarConexao`):

```js
  async function gerarSsoApiKey() {
    ssoGerando = true;
    try {
      const res = await api.gerarSsoApiKey(empresa.id);
      ssoApiKeyGerada = res.api_key;
    } catch (e) {
      erro = e.message || 'Erro ao gerar chave de API.';
    } finally {
      ssoGerando = false;
    }
  }

  async function testarSsoAcesso() {
    ssoTestando = true;
    ssoTesteStatus = null;
    try {
      const res = await api.testarSsoAcesso({
        empresa_id: empresa.id,
        query: empresa.sso_query_acesso,
        codigo_usuario: ssoTesteCodigoUsuario,
      });
      ssoTesteStatus = res.ok ? 'ok' : 'fail';
      ssoTesteResultado = res.ok
        ? (res.slugs.length ? `Painéis liberados: ${res.slugs.join(', ')}` : 'Nenhum painel liberado pra esse código')
        : `Falha: ${res.erro}`;
    } catch {
      ssoTesteStatus = 'fail';
      ssoTesteResultado = 'Erro ao testar a query.';
    } finally {
      ssoTestando = false;
    }
  }
```

No `salvar()` existente, incluir `sso_query_acesso` no `payload`:

```js
      const payload = {
        slug:    empresa.slug,
        nome:    empresa.nome,
        db_host: empresa.db_host,
        db_port: empresa.db_port,
        db_name: empresa.db_name,
        db_user: empresa.db_user,
        ativo:   empresa.ativo,
        sso_query_acesso: empresa.sso_query_acesso ?? null,
      };
```

No template, adicionar uma seção nova depois da seção "Conexão com o Banco" (antes de `{#if erro}`):

```svelte
      <section>
        <h3>SSO Externo</h3>

        <button
          class="btn-ghost btn-test"
          on:click={gerarSsoApiKey}
          disabled={ssoGerando}
        >
          {ssoGerando ? 'Gerando...' : 'Gerar/Regenerar Chave de API'}
        </button>

        {#if ssoApiKeyGerada}
          <p class="status-ok">
            Chave gerada — copie agora, não será mostrada de novo:<br />
            <code>{ssoApiKeyGerada}</code>
          </p>
        {/if}

        <label>
          Query de acesso (recebe $1 = codigo_usuario, devolve coluna painel_slug)
          <textarea
            bind:value={empresa.sso_query_acesso}
            rows="4"
            placeholder="SELECT painel_slug FROM minha_tabela WHERE codigo_usuario = $1"
          ></textarea>
        </label>

        <div class="row">
          <label style="flex:1">
            Código de usuário de exemplo
            <input bind:value={ssoTesteCodigoUsuario} placeholder="ex: user_123" />
          </label>
        </div>

        <button
          class="btn-ghost btn-test"
          on:click={testarSsoAcesso}
          disabled={ssoTestando || !empresa.sso_query_acesso || !ssoTesteCodigoUsuario}
        >
          {ssoTestando ? 'Testando...' : 'Testar Query'}
        </button>

        {#if ssoTesteStatus === 'ok'}
          <p class="status-ok">✓ {ssoTesteResultado}</p>
        {:else if ssoTesteStatus === 'fail'}
          <p class="status-fail">✗ {ssoTesteResultado}</p>
        {/if}
      </section>
```

Adicionar `textarea { font-family: monospace; font-size: 13px; padding: 8px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); color: var(--text); resize: vertical; }` ao `<style>` — as outras classes (`.btn-test`, `.status-ok`, `.status-fail`, `.row`) já existem na mesma tela.

- [ ] **Step 3: Rebuild e verificação manual**

Run:
```bash
docker restart datahub_backend datahub_frontend
```

Abrir `/configuracoes/empresas/{id}` de uma empresa (ex: alpha), clicar "Gerar/Regenerar Chave de API" (confirma que aparece uma vez), colar uma query de teste tipo `SELECT painel_slug FROM (VALUES ('user_1','algum_slug')) AS t(codigo_usuario, painel_slug) WHERE codigo_usuario = $1`, digitar `user_1` no campo de código de exemplo, clicar "Testar Query" (confirma que aparece "Painéis liberados: algum_slug"), salvar, recarregar a página e confirmar que a query salva reaparece na textarea.

Expected: fluxo completo funciona sem erros no console.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.js "frontend/src/routes/configuracoes/empresas/[id]/+page.svelte"
git commit -m "feat: add SSO config UI (API key + access query) to empresa edit screen"
```
