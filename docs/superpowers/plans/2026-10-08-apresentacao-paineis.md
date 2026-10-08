# Apresentação de Painéis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cadastro de "apresentações" (sequências de painéis existentes com filtros fixos e tempo por slide) e uma tela cheia que roda sozinha numa TV, com troca automática, rolagem automática, atualização periódica dos dados e renovação do token.

**Architecture:** 3 tabelas novas (`apresentacoes`, `apresentacao_slides`, `apresentacao_usuarios`) e um router FastAPI novo (`routes/apresentacoes.py`); `renderizar` de painéis é reaproveitado sem mudança. No front, a lógica pura (tokens de data, plano de rolagem, índices) vai para `lib/*.js` testados com `node --test`; o desenho do grid de indicadores é extraído da página de painel para `PainelGrid.svelte` e usado também pelo player (`ApresentacaoPlayer.svelte`).

**Tech Stack:** FastAPI + asyncpg (`query_meta`, `meta_tx`), pytest/TestClient contra o banco de dev; SvelteKit (sintaxe Svelte 4: `export let`, `on:click`, `$:`), testes `node:test`.

**Spec:** `docs/superpowers/specs/2026-10-08-apresentacao-paineis-design.md` (a Task 11 corrige nela quatro pontos descobertos na leitura do código, listados abaixo em "Ajustes sobre a spec").

## Ajustes sobre a spec (decididos ao ler o código)

1. `renderizar_painel` **não checa** `painel_usuarios` para usuários internos (só `externo` por slug). Logo **não há mudança** em `routes/paineis.py`.
2. Usuários `externo` (SSO) não usam apresentações: endpoints respondem 403 e o link do menu fica oculto.
3. Admin enxerga e executa todas as apresentações ativas da empresa (sem precisar estar em `apresentacao_usuarios`); usuário comum só as vinculadas. (Spec dizia "igual aos painéis", onde até admin precisa de vínculo.)
4. `filtros` do slide guardam **tokens crus** (`hoje`, `mes_atual_inicio`…). Eles são resolvidos a cada atualização, senão "hoje" ficaria velho numa TV ligada por dias. Só o que o usuário edita no preparo/execução vira valor fixo (override).
5. Limite de velocidade da rolagem é um **teto** (80 px/s, para ser legível), não um piso; se o teto impedir caber no tempo, o slide se estende.

## Global Constraints

- Slug de apresentação: só `[a-z0-9_]` (usa `_`, nunca `-`).
- `intervalo_atualizacao_seg` padrão 300, mínimo 30. `duracao_seg` padrão 30, mínimo 5.
- Delta SQL em `scripts/migrations/2026-10-08-apresentacoes.sql` + espelhado em `scripts/init-meta-prod.sql`; aplicado em prod **antes** do deploy.
- Sem mudança em `pdf-renderer`, Swarm ou `routes/paineis.py`.
- Token JWT dura 480 min; renovar a cada 30 min enquanto o player roda.
- Textos de UI em português; sem `uppercase` em títulos/rótulos.
- Commits terminam com as linhas de atribuição do ambiente (`Co-Authored-By` + `Claude-Session`).
- Rodar testes backend: `cd backend && python -m pytest tests/test_apresentacoes.py -v` (usa o Postgres de dev em `datahub_postgres`). Testes front: `cd frontend && node --test src/lib/`.

## Review Focus

- Apresentação sem slides ou só com painéis inativos: `/executar` devolve `slides: []` (tela mostra "Nenhum slide cadastrado"), sem 500. (Task 3)
- Usuário comum sem vínculo tentando `/executar`: 404. Usuário `externo`: 403. (Tasks 3, 4)
- Reordenação/PUT de slides com `painel_id` inexistente: 422 e a lista antiga permanece. (Task 2)
- Slug duplicado ou inválido: 409/422, não 500. (Task 2)
- Token em blacklist (logout) tentando `/auth/renovar`: 401. (Task 4)
- Conteúdo mais baixo que a tela: não rola e não estende o tempo; conteúdo gigante: velocidade limitada e tempo estendido. (Task 5)
- Virada de dia / de mês com tokens de data ("hoje" em 31/12 → 01/01). (Task 5)

---

## File Structure

**Criar**
- `scripts/migrations/2026-10-08-apresentacoes.sql` — delta das 3 tabelas.
- `backend/routes/apresentacoes.py` — todo o router.
- `backend/tests/test_apresentacoes.py` — testes do router + `/auth/renovar`.
- `frontend/src/lib/filtrosPainel.js` (+ `.test.js`) — tokens de data e filtros iniciais.
- `frontend/src/lib/apresentacao.js` (+ `.test.js`) — plano de rolagem, índices, atualização.
- `frontend/src/lib/components/PainelGrid.svelte` — grid de indicadores extraído.
- `frontend/src/lib/components/ApresentacaoPlayer.svelte` — o player em tela cheia.
- `frontend/src/routes/apresentar/+page.svelte` — lista para o usuário.
- `frontend/src/routes/apresentar/[id]/+page.svelte` — preparo + player.
- `frontend/src/routes/configuracoes/apresentacoes/+page.svelte` — lista admin.
- `frontend/src/routes/configuracoes/apresentacoes/[id]/+page.svelte` — form admin (`nova` = criação).

**Modificar**
- `scripts/init-meta-prod.sql` — espelha as tabelas.
- `backend/main.py` — registra o router.
- `backend/routes/auth.py` — `POST /api/auth/renovar`.
- `backend/tests/conftest.py` — `hard_delete_apresentacao`.
- `frontend/src/lib/api.js` — métodos novos.
- `frontend/src/routes/painel/[slug]/+page.svelte` — usa `PainelGrid` e `filtrosPainel.js`.
- `frontend/src/routes/+layout.svelte` — menu + rota sem shell.
- `README.md` — seção curta.

---

### Task 1: Schema (delta + init + aplicar no banco de dev)

**Files:**
- Create: `scripts/migrations/2026-10-08-apresentacoes.sql`
- Modify: `scripts/init-meta-prod.sql` (inserir logo após o bloco `painel_usuarios`/`idx_painel_usr_usuario`, antes de `CREATE TABLE chat_historico`)

**Interfaces:**
- Produces: tabelas `apresentacoes(id, slug, nome, descricao, empresa_id, intervalo_atualizacao_seg, ativo, criado_em, atualizado_em)`, `apresentacao_slides(id, apresentacao_id, painel_id, ordem, duracao_seg, filtros jsonb)`, `apresentacao_usuarios(apresentacao_id, usuario_id)`.

- [ ] **Step 1: Criar o delta**

```sql
-- Apresentação de painéis (TV): sequência de painéis existentes com filtros fixos e
-- tempo por slide. Rodar no datahub_meta de cada ambiente ANTES do deploy.
CREATE TABLE IF NOT EXISTS apresentacoes (
    id                         SERIAL PRIMARY KEY,
    slug                       VARCHAR(100) UNIQUE NOT NULL,
    nome                       VARCHAR(150) NOT NULL,
    descricao                  TEXT,
    empresa_id                 INTEGER REFERENCES empresas(id),
    intervalo_atualizacao_seg  INTEGER NOT NULL DEFAULT 300,
    ativo                      BOOLEAN NOT NULL DEFAULT true,
    criado_em                  TIMESTAMP DEFAULT NOW(),
    atualizado_em              TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS apresentacao_slides (
    id              SERIAL PRIMARY KEY,
    apresentacao_id INTEGER NOT NULL REFERENCES apresentacoes(id) ON DELETE CASCADE,
    painel_id       INTEGER NOT NULL REFERENCES paineis(id) ON DELETE CASCADE,
    ordem           INTEGER NOT NULL DEFAULT 0,
    duracao_seg     INTEGER NOT NULL DEFAULT 30,
    filtros         JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_apres_slides_apres ON apresentacao_slides(apresentacao_id, ordem);

CREATE TABLE IF NOT EXISTS apresentacao_usuarios (
    apresentacao_id INTEGER NOT NULL REFERENCES apresentacoes(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY (apresentacao_id, usuario_id)
);
CREATE INDEX IF NOT EXISTS idx_apres_usr_usuario ON apresentacao_usuarios(usuario_id);

DROP TRIGGER IF EXISTS trg_apresentacoes_updated ON apresentacoes;
CREATE TRIGGER trg_apresentacoes_updated
BEFORE UPDATE ON apresentacoes
FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();
```

- [ ] **Step 2: Espelhar o mesmo SQL (sem `IF NOT EXISTS`/`DROP TRIGGER` desnecessários é aceitável; pode colar idêntico) em `scripts/init-meta-prod.sql`** no ponto indicado em Files.

- [ ] **Step 3: Aplicar no banco de dev**

Run: `docker exec -i datahub_postgres psql -U postgres -d datahub_meta < scripts/migrations/2026-10-08-apresentacoes.sql`
Expected: `CREATE TABLE` ×3, `CREATE INDEX` ×2, `CREATE TRIGGER`. (Se o dono das tabelas precisar ser `datahub_user`, rode também `GRANT SELECT,INSERT,UPDATE,DELETE ON apresentacoes, apresentacao_slides, apresentacao_usuarios TO datahub_user; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO datahub_user;` — compare com como `permissao_ids` foi tratada em `scripts/migrations/2026-09-23-permissao-ids.sql`.)

- [ ] **Step 4: Verificar que o usuário da aplicação enxerga as tabelas**

Run: `docker exec -i datahub_postgres psql -U datahub_user -d datahub_meta -c "SELECT count(*) FROM apresentacoes"`
Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/2026-10-08-apresentacoes.sql scripts/init-meta-prod.sql
git commit -m "feat: tabelas de apresentacao de paineis (delta + init)"
```

---

### Task 2: Router — CRUD de apresentações, slides e usuários

**Files:**
- Create: `backend/routes/apresentacoes.py`, `backend/tests/test_apresentacoes.py`
- Modify: `backend/main.py` (import + `app.include_router(apresentacoes.router)`), `backend/tests/conftest.py`

**Interfaces:**
- Produces (HTTP, todas exigem JWT; admin salvo onde dito):
  - `POST /api/apresentacoes/` body `{slug,nome,descricao?,empresa_id?,intervalo_atualizacao_seg?=300,ativo?=true}` → apresentação (dict com `id`).
  - `GET /api/apresentacoes/` (admin) → lista (todas, inclui inativas) com `total_slides`.
  - `GET /api/apresentacoes/{id}` (admin) → apresentação.
  - `PATCH /api/apresentacoes/{id}` (admin) body parcial → apresentação.
  - `DELETE /api/apresentacoes/{id}` (admin) → desativa (`ativo=false`). `DELETE /api/apresentacoes/{id}/permanente` (admin) → apaga.
  - `GET /api/apresentacoes/{id}/slides` (admin) → `[{id,painel_id,ordem,duracao_seg,filtros:{},painel_nome,painel_slug,painel_ativo}]`.
  - `PUT /api/apresentacoes/{id}/slides` (admin) body `[{painel_id,duracao_seg?=30,filtros?={}}]` → mesma lista; `ordem` = índice.
  - `GET/PUT /api/apresentacoes/{id}/usuarios` (admin) — GET → `[{id,nome,email,role}]`; PUT body `[int]` → `{ok,usuarios}`.
- Produces (Python): `conftest.hard_delete_apresentacao(id)`.

- [ ] **Step 1: Adicionar helper no `conftest.py`** (junto dos outros `hard_delete_*`)

```python
def hard_delete_apresentacao(apresentacao_id: int):
    """Remove de verdade uma apresentação criada em teste (slides e usuários
    saem por cascade) -- o DELETE da API só desativa."""
    async def _exec():
        conn = await _connect_meta()
        try:
            await conn.execute("DELETE FROM apresentacoes WHERE id = $1", apresentacao_id)
        finally:
            await conn.close()
    asyncio.run(_exec())
```

- [ ] **Step 2: Escrever os testes que falham** (`backend/tests/test_apresentacoes.py`)

```python
import uuid
import pytest
from conftest import hard_delete_apresentacao, hard_delete_painel


def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def painel_id(client, auth_token):
    res = client.post(
        "/api/paineis/",
        json={"slug": f"painel_apr_{uuid.uuid4().hex[:8]}", "nome": "Painel p/ Apresentação"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    pid = res.json()["id"]
    yield pid
    hard_delete_painel(pid)


@pytest.fixture
def apresentacao(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": f"apr_{uuid.uuid4().hex[:8]}", "nome": "TV Teste"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    apr = res.json()
    yield apr
    hard_delete_apresentacao(apr["id"])


def test_criar_apresentacao_usa_padroes(apresentacao):
    assert apresentacao["intervalo_atualizacao_seg"] == 300
    assert apresentacao["ativo"] is True
    assert apresentacao["empresa_id"] is None


def test_slug_invalido_retorna_422(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": "Com-Hifen", "nome": "x"},
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_slug_duplicado_retorna_409(client, auth_token, apresentacao):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": apresentacao["slug"], "nome": "outra"},
        headers=H(auth_token),
    )
    assert res.status_code == 409


def test_intervalo_menor_que_30_retorna_422(client, auth_token):
    res = client.post(
        "/api/apresentacoes/",
        json={"slug": f"apr_{uuid.uuid4().hex[:8]}", "nome": "x", "intervalo_atualizacao_seg": 10},
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_patch_atualiza_campos(client, auth_token, apresentacao):
    res = client.patch(
        f"/api/apresentacoes/{apresentacao['id']}",
        json={"nome": "Novo nome", "intervalo_atualizacao_seg": 60},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    assert res.json()["nome"] == "Novo nome"
    assert res.json()["intervalo_atualizacao_seg"] == 60


def test_delete_desativa(client, auth_token, apresentacao):
    res = client.delete(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token))
    assert res.status_code == 200
    got = client.get(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token)).json()
    assert got["ativo"] is False


def test_salvar_slides_grava_ordem_e_filtros(client, auth_token, apresentacao, painel_id):
    corpo = [
        {"painel_id": painel_id, "duracao_seg": 20, "filtros": {"data_inicio": "mes_atual_inicio"}},
        {"painel_id": painel_id, "duracao_seg": 45, "filtros": {}},
    ]
    res = client.put(f"/api/apresentacoes/{apresentacao['id']}/slides", json=corpo, headers=H(auth_token))
    assert res.status_code == 200
    slides = client.get(f"/api/apresentacoes/{apresentacao['id']}/slides", headers=H(auth_token)).json()
    assert [s["ordem"] for s in slides] == [0, 1]
    assert [s["duracao_seg"] for s in slides] == [20, 45]
    assert slides[0]["filtros"] == {"data_inicio": "mes_atual_inicio"}
    assert slides[0]["painel_ativo"] is True


def test_salvar_slides_com_painel_inexistente_retorna_422_e_mantem_lista(client, auth_token, apresentacao, painel_id):
    url = f"/api/apresentacoes/{apresentacao['id']}/slides"
    client.put(url, json=[{"painel_id": painel_id}], headers=H(auth_token))
    res = client.put(url, json=[{"painel_id": 99999999}], headers=H(auth_token))
    assert res.status_code == 422
    assert len(client.get(url, headers=H(auth_token)).json()) == 1


def test_duracao_menor_que_5_retorna_422(client, auth_token, apresentacao, painel_id):
    res = client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id, "duracao_seg": 1}],
        headers=H(auth_token),
    )
    assert res.status_code == 422


def test_salvar_e_listar_usuarios(client, auth_token, apresentacao):
    me = client.get("/api/auth/me", headers=H(auth_token)).json()
    res = client.put(f"/api/apresentacoes/{apresentacao['id']}/usuarios", json=[me["id"]], headers=H(auth_token))
    assert res.status_code == 200
    lista = client.get(f"/api/apresentacoes/{apresentacao['id']}/usuarios", headers=H(auth_token)).json()
    assert [u["id"] for u in lista] == [me["id"]]
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_apresentacoes.py -v`
Expected: FAIL (404 nas rotas / `ModuleNotFoundError`).

- [ ] **Step 4: Implementar `backend/routes/apresentacoes.py`**

```python
import json
import logging
import re
from typing import Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config.databases import query_meta, meta_tx
from middleware.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/apresentacoes", tags=["Apresentações"])
logger = logging.getLogger("datahub")

SLUG_RE = re.compile(r"^[a-z0-9_]+$")
CAMPOS_EDITAVEIS = {"slug", "nome", "descricao", "empresa_id", "intervalo_atualizacao_seg", "ativo"}


class ApresentacaoInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    empresa_id: Optional[int] = None
    intervalo_atualizacao_seg: int = Field(300, ge=30, le=86400)
    ativo: bool = True


class SlideInput(BaseModel):
    painel_id: int
    duracao_seg: int = Field(30, ge=5, le=3600)
    filtros: Dict[str, str] = {}


def _bloquear_externo(user):
    if user["role"] == "externo":
        raise HTTPException(403, "Apresentações não estão disponíveis para este perfil")


def _validar_slug(slug: str):
    if not SLUG_RE.match(slug):
        raise HTTPException(422, "Slug deve conter apenas letras minúsculas, números e _")


def _slide_dict(row, extra_painel: bool = False) -> dict:
    d = dict(row)
    d["filtros"] = json.loads(d["filtros"]) if d.get("filtros") else {}
    return d


# ── Rotas do usuário (estáticas antes das dinâmicas) ─────────

@router.get("/minhas")
async def minhas(user=Depends(get_current_user)):
    _bloquear_externo(user)
    base = """
        SELECT a.id, a.slug, a.nome, a.descricao,
               (SELECT COUNT(*)::int FROM apresentacao_slides s WHERE s.apresentacao_id = a.id) AS total_slides
        FROM apresentacoes a
    """
    if user["role"] == "admin":
        rows = await query_meta(base + """
            WHERE a.ativo = true AND (a.empresa_id = $1 OR a.empresa_id IS NULL)
            ORDER BY a.nome
        """, user["empresa_id"])
    else:
        rows = await query_meta(base + """
            JOIN apresentacao_usuarios au ON au.apresentacao_id = a.id
            WHERE au.usuario_id = $1 AND a.ativo = true
              AND (a.empresa_id = $2 OR a.empresa_id IS NULL)
            ORDER BY a.nome
        """, user["id"], user["empresa_id"])
    return [dict(r) for r in rows]


@router.get("/{apresentacao_id}/executar")
async def executar(apresentacao_id: int, user=Depends(get_current_user)):
    _bloquear_externo(user)
    rows = await query_meta("""
        SELECT id, slug, nome, descricao, intervalo_atualizacao_seg
        FROM apresentacoes
        WHERE id = $1 AND ativo = true AND (empresa_id = $2 OR empresa_id IS NULL)
    """, apresentacao_id, user["empresa_id"])
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada ou sem acesso")
    if user["role"] != "admin":
        vinculo = await query_meta(
            "SELECT 1 FROM apresentacao_usuarios WHERE apresentacao_id = $1 AND usuario_id = $2",
            apresentacao_id, user["id"],
        )
        if not vinculo:
            raise HTTPException(404, "Apresentação não encontrada ou sem acesso")

    slides_rows = await query_meta("""
        SELECT s.id, s.ordem, s.duracao_seg, s.filtros::text AS filtros,
               p.id AS p_id, p.slug AS p_slug, p.nome AS p_nome,
               p.descricao AS p_descricao, p.colunas AS p_colunas
        FROM apresentacao_slides s
        JOIN paineis p ON p.id = s.painel_id
        WHERE s.apresentacao_id = $1 AND p.ativo = true
          AND (p.empresa_id = $2 OR p.empresa_id IS NULL)
        ORDER BY s.ordem, s.id
    """, apresentacao_id, user["empresa_id"])
    slides = []
    for r in slides_rows:
        slides.append({
            "id": r["id"],
            "ordem": r["ordem"],
            "duracao_seg": r["duracao_seg"],
            "filtros": json.loads(r["filtros"]) if r["filtros"] else {},
            "painel": {
                "id": r["p_id"], "slug": r["p_slug"], "nome": r["p_nome"],
                "descricao": r["p_descricao"], "colunas": r["p_colunas"],
            },
        })
    return {**dict(rows[0]), "slides": slides}


# ── CRUD (admin) ─────────────────────────────────────────────

@router.get("/")
async def listar(user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT a.*,
               (SELECT COUNT(*)::int FROM apresentacao_slides s WHERE s.apresentacao_id = a.id) AS total_slides
        FROM apresentacoes a
        ORDER BY a.nome
    """)
    return [dict(r) for r in rows]


@router.post("/")
async def criar(body: ApresentacaoInput, user=Depends(require_admin)):
    _validar_slug(body.slug)
    try:
        rows = await query_meta("""
            INSERT INTO apresentacoes (slug, nome, descricao, empresa_id, intervalo_atualizacao_seg, ativo)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING *
        """, body.slug, body.nome, body.descricao, body.empresa_id,
            body.intervalo_atualizacao_seg, body.ativo)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Já existe uma apresentação com esse slug")
    return dict(rows[0])


@router.get("/{apresentacao_id}")
async def buscar(apresentacao_id: int, user=Depends(require_admin)):
    rows = await query_meta("SELECT * FROM apresentacoes WHERE id = $1", apresentacao_id)
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada")
    return dict(rows[0])


@router.patch("/{apresentacao_id}")
async def atualizar(apresentacao_id: int, body: dict, user=Depends(require_admin)):
    campos = {k: v for k, v in body.items() if k in CAMPOS_EDITAVEIS}
    if not campos:
        raise HTTPException(400, "Nenhum campo válido para atualizar")
    if "slug" in campos:
        _validar_slug(campos["slug"])
    if "intervalo_atualizacao_seg" in campos and int(campos["intervalo_atualizacao_seg"]) < 30:
        raise HTTPException(422, "Intervalo mínimo é 30 segundos")
    sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(campos))  # chaves vêm da whitelist
    try:
        rows = await query_meta(
            f"UPDATE apresentacoes SET {sets} WHERE id = $1 RETURNING *",
            apresentacao_id, *campos.values(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Já existe uma apresentação com esse slug")
    if not rows:
        raise HTTPException(404, "Apresentação não encontrada")
    return dict(rows[0])


@router.delete("/{apresentacao_id}")
async def desativar(apresentacao_id: int, user=Depends(require_admin)):
    await query_meta("UPDATE apresentacoes SET ativo = false WHERE id = $1", apresentacao_id)
    return {"ok": True}


@router.delete("/{apresentacao_id}/permanente")
async def deletar_permanente(apresentacao_id: int, user=Depends(require_admin)):
    await query_meta("DELETE FROM apresentacoes WHERE id = $1", apresentacao_id)
    return {"ok": True}


# ── Slides ───────────────────────────────────────────────────

async def _listar_slides(apresentacao_id: int) -> list:
    rows = await query_meta("""
        SELECT s.id, s.painel_id, s.ordem, s.duracao_seg, s.filtros::text AS filtros,
               p.nome AS painel_nome, p.slug AS painel_slug, p.ativo AS painel_ativo
        FROM apresentacao_slides s
        JOIN paineis p ON p.id = s.painel_id
        WHERE s.apresentacao_id = $1
        ORDER BY s.ordem, s.id
    """, apresentacao_id)
    return [_slide_dict(r) for r in rows]


@router.get("/{apresentacao_id}/slides")
async def listar_slides(apresentacao_id: int, user=Depends(require_admin)):
    return await _listar_slides(apresentacao_id)


@router.put("/{apresentacao_id}/slides")
async def salvar_slides(apresentacao_id: int, slides: List[SlideInput], user=Depends(require_admin)):
    existe = await query_meta("SELECT 1 FROM apresentacoes WHERE id = $1", apresentacao_id)
    if not existe:
        raise HTTPException(404, "Apresentação não encontrada")
    ids = list({s.painel_id for s in slides})
    if ids:
        achados = await query_meta("SELECT id FROM paineis WHERE id = ANY($1::int[])", ids)
        if len(achados) != len(ids):
            raise HTTPException(422, "Há slide apontando para um painel que não existe")
    async with meta_tx() as conn:
        await conn.execute("DELETE FROM apresentacao_slides WHERE apresentacao_id = $1", apresentacao_id)
        for i, s in enumerate(slides):
            await conn.execute("""
                INSERT INTO apresentacao_slides (apresentacao_id, painel_id, ordem, duracao_seg, filtros)
                VALUES ($1,$2,$3,$4,$5::jsonb)
            """, apresentacao_id, s.painel_id, i, s.duracao_seg, json.dumps(s.filtros))
    return await _listar_slides(apresentacao_id)


# ── Usuários com acesso ──────────────────────────────────────

@router.get("/{apresentacao_id}/usuarios")
async def listar_usuarios(apresentacao_id: int, user=Depends(require_admin)):
    rows = await query_meta("""
        SELECT u.id, u.nome, u.email, u.role
        FROM usuarios u
        JOIN apresentacao_usuarios au ON au.usuario_id = u.id
        WHERE au.apresentacao_id = $1
    """, apresentacao_id)
    return [dict(r) for r in rows]


@router.put("/{apresentacao_id}/usuarios")
async def salvar_usuarios(apresentacao_id: int, usuario_ids: List[int], user=Depends(require_admin)):
    async with meta_tx() as conn:
        await conn.execute("DELETE FROM apresentacao_usuarios WHERE apresentacao_id = $1", apresentacao_id)
        for uid in usuario_ids:
            await conn.execute(
                "INSERT INTO apresentacao_usuarios (apresentacao_id, usuario_id) VALUES ($1,$2)",
                apresentacao_id, uid,
            )
    return {"ok": True, "usuarios": usuario_ids}
```

Em `backend/main.py`: acrescentar `apresentacoes` ao `from routes import ...` e `app.include_router(apresentacoes.router)` depois de `paineis.router`.

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_apresentacoes.py -v`
Expected: todos PASS (reinicie o backend de dev antes se estiver rodando com reload desligado).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/apresentacoes.py backend/main.py backend/tests/conftest.py backend/tests/test_apresentacoes.py
git commit -m "feat: API de apresentacoes (CRUD, slides, usuarios)"
```

---

### Task 3: Endpoints do usuário — `/minhas` e `/executar` (testes)

O código já foi escrito na Task 2 (junto do router); esta task só o prova com testes, incluindo permissões.

**Files:**
- Modify: `backend/tests/test_apresentacoes.py` (acrescentar ao final)

**Interfaces:**
- Consumes: fixtures `apresentacao`, `painel_id`, `H` da Task 2; `hard_delete_usuario` do conftest.

- [ ] **Step 1: Escrever os testes**

```python
from conftest import hard_delete_usuario


@pytest.fixture
def usuario_comum(client, auth_token):
    alpha = next(
        e for e in client.get("/api/empresas/", headers=H(auth_token)).json() if e["slug"] == "alpha"
    )
    email = f"apr_{uuid.uuid4().hex[:8]}@datahub.local"
    senha = "senha12345"
    res = client.post(
        "/api/usuarios/",
        json={"nome": "Viewer Apr", "email": email, "senha": senha, "role": "viewer"},
        headers=H(auth_token),
    )
    assert res.status_code == 200
    uid = res.json()["id"]
    vinc = client.post(
        f"/api/usuarios/{uid}/empresas",
        json={"vinculos": [{"empresa_id": alpha["id"]}]},
        headers=H(auth_token),
    )
    assert vinc.status_code == 200
    login = client.post("/api/auth/login", json={"email": email, "senha": senha}).json()
    sel = client.post(
        "/api/auth/selecionar-empresa",
        json={"session_token": login["session_token"], "empresa_id": alpha["id"]},
    ).json()
    yield {"id": uid, "token": sel["token"]}
    hard_delete_usuario(uid)


def test_executar_sem_slides_devolve_lista_vazia(client, auth_token, apresentacao):
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    assert res.status_code == 200
    assert res.json()["slides"] == []


def test_executar_devolve_slides_em_ordem_com_painel(client, auth_token, apresentacao, painel_id):
    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id, "duracao_seg": 12, "filtros": {"hoje": "hoje"}}],
        headers=H(auth_token),
    )
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    body = res.json()
    assert body["intervalo_atualizacao_seg"] == 300
    assert body["slides"][0]["duracao_seg"] == 12
    assert body["slides"][0]["filtros"] == {"hoje": "hoje"}
    assert body["slides"][0]["painel"]["id"] == painel_id


def test_executar_pula_painel_inativo(client, auth_token, apresentacao, painel_id):
    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/slides",
        json=[{"painel_id": painel_id}],
        headers=H(auth_token),
    )
    client.delete(f"/api/paineis/{painel_id}", headers=H(auth_token))  # desativa
    res = client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=H(auth_token))
    assert res.status_code == 200
    assert res.json()["slides"] == []


def test_minhas_admin_ve_todas_as_ativas(client, auth_token, apresentacao):
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=H(auth_token)).json()]
    assert apresentacao["id"] in ids


def test_minhas_ignora_inativas(client, auth_token, apresentacao):
    client.delete(f"/api/apresentacoes/{apresentacao['id']}", headers=H(auth_token))
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=H(auth_token)).json()]
    assert apresentacao["id"] not in ids


def test_usuario_comum_so_ve_e_executa_as_vinculadas(client, auth_token, apresentacao, usuario_comum):
    h = H(usuario_comum["token"])
    antes = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=h).json()]
    assert apresentacao["id"] not in antes
    assert client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=h).status_code == 404

    client.put(
        f"/api/apresentacoes/{apresentacao['id']}/usuarios",
        json=[usuario_comum["id"]],
        headers=H(auth_token),
    )
    ids = [a["id"] for a in client.get("/api/apresentacoes/minhas", headers=h).json()]
    assert apresentacao["id"] in ids
    assert client.get(f"/api/apresentacoes/{apresentacao['id']}/executar", headers=h).status_code == 200


def test_usuario_comum_nao_administra(client, usuario_comum):
    res = client.post(
        "/api/apresentacoes/", json={"slug": "x_y", "nome": "x"}, headers=H(usuario_comum["token"])
    )
    assert res.status_code == 403
```

- [ ] **Step 2: Rodar**

Run: `cd backend && python -m pytest tests/test_apresentacoes.py -v`
Expected: PASS. Se algum falhar, corrija o router (não o teste) a menos que o teste esteja errado.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_apresentacoes.py
git commit -m "test: permissoes e execucao de apresentacoes"
```

---

### Task 4: `POST /api/auth/renovar`

**Files:**
- Modify: `backend/routes/auth.py` (nova rota depois de `/me`), `backend/tests/test_apresentacoes.py`

**Interfaces:**
- Produces: `POST /api/auth/renovar` (JWT) → `{"token": str, "token_type": "bearer"}`; 403 para `externo`; 401 se token inválido/blacklist (via `get_current_user`).

- [ ] **Step 1: Teste que falha** (acrescentar a `test_apresentacoes.py`)

```python
from jose import jwt as jose_jwt
from config.settings import settings


def test_renovar_devolve_token_valido_com_mesmos_dados(client, auth_token):
    res = client.post("/api/auth/renovar", headers=H(auth_token))
    assert res.status_code == 200
    novo = res.json()["token"]
    antigo = jose_jwt.decode(auth_token, settings.JWT_SECRET, algorithms=["HS256"])
    claims = jose_jwt.decode(novo, settings.JWT_SECRET, algorithms=["HS256"])
    for k in ("user_id", "empresa_id", "company_slug", "role"):
        assert claims[k] == antigo[k]
    assert client.get("/api/auth/me", headers=H(novo)).status_code == 200


def test_renovar_exige_token(client):
    assert client.post("/api/auth/renovar").status_code in (401, 403)


def test_renovar_com_logout_retorna_401(client, auth_token):
    client.post("/api/auth/logout", headers=H(auth_token))
    try:
        assert client.post("/api/auth/renovar", headers=H(auth_token)).status_code == 401
    finally:
        # novo login limpa a blacklist (selecionar-empresa faz DEL), não deixa o admin de dev bloqueado
        login = client.post("/api/auth/login", json={"email": "admin@datahub.local", "senha": "admin123"}).json()
        emp = next(e for e in login["empresas"] if e["slug"] == "alpha")
        client.post("/api/auth/selecionar-empresa", json={"session_token": login["session_token"], "empresa_id": emp["id"]})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && python -m pytest tests/test_apresentacoes.py -k renovar -v`
Expected: FAIL (404/405).

- [ ] **Step 3: Implementar** em `auth.py`, logo após a rota `/me`:

```python
@router.post("/renovar")
async def renovar_token(user=Depends(get_current_user)):
    """Emite um token novo com os mesmos dados enquanto o atual for válido.
    Usado pela tela de apresentação (TV) pra não cair em 'sessão expirada'."""
    if user["role"] == "externo":
        raise HTTPException(status_code=403, detail="Renovação indisponível para este perfil")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "user_id": user["id"],
            "empresa_id": user["empresa_id"],
            "company_slug": user["company_slug"],
            "nome": user["nome"],
            "role": user["role"],
            "exp": expire,
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return {"token": token, "token_type": "bearer"}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && python -m pytest tests/test_apresentacoes.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/auth.py backend/tests/test_apresentacoes.py
git commit -m "feat: endpoint de renovacao de token para a apresentacao"
```

---

### Task 5: Lógica pura do front — `filtrosPainel.js` e `apresentacao.js`

**Files:**
- Create: `frontend/src/lib/filtrosPainel.js`, `frontend/src/lib/filtrosPainel.test.js`, `frontend/src/lib/apresentacao.js`, `frontend/src/lib/apresentacao.test.js`

**Interfaces:**
- Produces (`filtrosPainel.js`):
  - `resolverToken(val: string, agora?: Date): string`
  - `valoresIniciais(variaveis: Array, agora?: Date): Record<string,string>`
  - `resolverFiltros(filtros: Record<string,string>, agora?: Date): Record<string,string>`
  - `chavesFiltro(variavel): Array<{chave:string, rotulo:string}>`
- Produces (`apresentacao.js`):
  - `PAUSA_ROLAGEM_SEG = 3`, `VELOCIDADE_MAX_PX_SEG = 80`, `RENOVAR_TOKEN_MS = 30*60*1000`
  - `planoRolagem({alturaConteudo, alturaViewport, duracaoSeg}) → {rola, distancia, velocidade, duracaoRolagemSeg, tempoTotalSeg}`
  - `posicaoRolagem(plano, decorridoSeg) → number (px)`
  - `proximoIndice(atual, total)`, `anteriorIndice(atual, total)`
  - `precisaAtualizar(ultimaMs, agoraMs, intervaloSeg) → boolean`
  - `filtrosEfetivos(raw, override, agora?) → Record<string,string>`

- [ ] **Step 1: Teste de `filtrosPainel`**

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolverToken, valoresIniciais, resolverFiltros, chavesFiltro } from './filtrosPainel.js';

const OUT_8 = new Date(2026, 9, 8); // 08/10/2026

test('tokens do mês e do dia', () => {
  assert.equal(resolverToken('hoje', OUT_8), '2026-10-08');
  assert.equal(resolverToken('ontem', OUT_8), '2026-10-07');
  assert.equal(resolverToken('mes_atual_inicio', OUT_8), '2026-10-01');
  assert.equal(resolverToken('mes_atual_fim', OUT_8), '2026-10-31');
  assert.equal(resolverToken('mes_anterior_inicio', OUT_8), '2026-09-01');
  assert.equal(resolverToken('mes_anterior_fim', OUT_8), '2026-09-30');
  assert.equal(resolverToken('ano_atual_inicio', OUT_8), '2026-01-01');
  assert.equal(resolverToken('ano_atual_fim', OUT_8), '2026-12-31');
});

test('janeiro olha dezembro do ano anterior; virada de ano em "ontem"', () => {
  const jan = new Date(2026, 0, 1);
  assert.equal(resolverToken('mes_anterior_inicio', jan), '2025-12-01');
  assert.equal(resolverToken('mes_anterior_fim', jan), '2025-12-31');
  assert.equal(resolverToken('ontem', jan), '2025-12-31');
});

test('valor que não é token passa direto; vazio vira string vazia', () => {
  assert.equal(resolverToken('Lavoura', OUT_8), 'Lavoura');
  assert.equal(resolverToken('', OUT_8), '');
  assert.equal(resolverToken(undefined, OUT_8), '');
});

test('valoresIniciais separa date_range em _inicio/_fim', () => {
  const v = valoresIniciais([
    { tipo: 'date_range', slug: 'periodo', valor_padrao_inicio: 'mes_atual_inicio', valor_padrao_fim: 'hoje' },
    { tipo: 'text', slug: 'busca', valor_padrao: 'abc' },
    { tipo: 'select', slug: 'setor' },
  ], OUT_8);
  assert.deepEqual(v, { periodo_inicio: '2026-10-01', periodo_fim: '2026-10-08', busca: 'abc', setor: '' });
});

test('resolverFiltros resolve todos os valores', () => {
  assert.deepEqual(
    resolverFiltros({ periodo_inicio: 'mes_atual_inicio', setor: 'Lavoura' }, OUT_8),
    { periodo_inicio: '2026-10-01', setor: 'Lavoura' },
  );
  assert.deepEqual(resolverFiltros(undefined, OUT_8), {});
});

test('chavesFiltro', () => {
  assert.deepEqual(
    chavesFiltro({ tipo: 'date_range', slug: 'periodo', nome: 'Período' }).map(c => c.chave),
    ['periodo_inicio', 'periodo_fim'],
  );
  assert.deepEqual(chavesFiltro({ tipo: 'select', slug: 'setor', nome: 'Setor' }), [{ chave: 'setor', rotulo: 'Setor' }]);
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && node --test src/lib/filtrosPainel.test.js`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar `filtrosPainel.js`** (a lógica de `resolverToken`/`valoresIniciais` é movida da página de painel, parametrizando a data)

```js
// Tokens de data usados nos valores padrão dos filtros ("hoje", "mes_atual_inicio"...).
const fmt = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

export function resolverToken(val, agora = new Date()) {
  if (!val) return '';
  const ano = agora.getFullYear(), mes = agora.getMonth() + 1;
  const ultimoDia = new Date(ano, mes, 0).getDate();
  const mesAnt = mes === 1 ? 12 : mes - 1;
  const anoAnt = mes === 1 ? ano - 1 : ano;
  const ultimoDiaMesAnt = new Date(anoAnt, mesAnt, 0).getDate();
  const tokens = {
    hoje: fmt(ano, mes, agora.getDate()),
    ontem: (() => { const d = new Date(agora); d.setDate(d.getDate() - 1); return fmt(d.getFullYear(), d.getMonth() + 1, d.getDate()); })(),
    mes_atual_inicio: fmt(ano, mes, 1),
    mes_atual_fim: fmt(ano, mes, ultimoDia),
    mes_anterior_inicio: fmt(anoAnt, mesAnt, 1),
    mes_anterior_fim: fmt(anoAnt, mesAnt, ultimoDiaMesAnt),
    ano_atual_inicio: fmt(ano, 1, 1),
    ano_atual_fim: fmt(ano, 12, 31),
  };
  return tokens[val] ?? val;
}

export function valoresIniciais(variaveis, agora = new Date()) {
  const v = {};
  variaveis.forEach(variavel => {
    if (variavel.tipo === 'date_range') {
      v[variavel.slug + '_inicio'] = resolverToken(variavel.valor_padrao_inicio || '', agora);
      v[variavel.slug + '_fim'] = resolverToken(variavel.valor_padrao_fim || '', agora);
    } else {
      v[variavel.slug] = resolverToken(variavel.valor_padrao || '', agora);
    }
  });
  return v;
}

export function resolverFiltros(filtros, agora = new Date()) {
  const r = {};
  for (const [k, v] of Object.entries(filtros ?? {})) r[k] = resolverToken(v, agora);
  return r;
}

// Chaves de parâmetro que uma variável produz (date_range gera duas).
export function chavesFiltro(variavel) {
  if (variavel.tipo === 'date_range') {
    return [
      { chave: variavel.slug + '_inicio', rotulo: `${variavel.nome} (início)` },
      { chave: variavel.slug + '_fim', rotulo: `${variavel.nome} (fim)` },
    ];
  }
  return [{ chave: variavel.slug, rotulo: variavel.nome }];
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && node --test src/lib/filtrosPainel.test.js`
Expected: PASS.

- [ ] **Step 5: Teste de `apresentacao.js`**

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PAUSA_ROLAGEM_SEG, VELOCIDADE_MAX_PX_SEG,
  planoRolagem, posicaoRolagem, proximoIndice, anteriorIndice, precisaAtualizar, filtrosEfetivos,
} from './apresentacao.js';

const perto = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test('conteúdo que cabe na tela não rola nem estende o tempo', () => {
  const p = planoRolagem({ alturaConteudo: 800, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.rola, false);
  assert.equal(p.tempoTotalSeg, 30);
  assert.equal(posicaoRolagem(p, 15), 0);
});

test('diferença de 1px (arredondamento) não conta como rolagem', () => {
  assert.equal(planoRolagem({ alturaConteudo: 901, alturaViewport: 900, duracaoSeg: 30 }).rola, false);
});

test('rolagem cabe no tempo configurado (descontadas as pausas)', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.rola, true);
  assert.equal(p.distancia, 1000);
  perto(p.velocidade, 1000 / (30 - 2 * PAUSA_ROLAGEM_SEG));
  assert.equal(p.tempoTotalSeg, 30);
});

test('conteúdo gigante: velocidade limitada ao teto e tempo estendido', () => {
  const p = planoRolagem({ alturaConteudo: 9900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(p.velocidade, VELOCIDADE_MAX_PX_SEG);
  perto(p.duracaoRolagemSeg, 9000 / VELOCIDADE_MAX_PX_SEG);
  perto(p.tempoTotalSeg, 9000 / VELOCIDADE_MAX_PX_SEG + 2 * PAUSA_ROLAGEM_SEG);
  assert.ok(p.tempoTotalSeg > 30);
});

test('duração curta (5s) não gera velocidade infinita', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 5 });
  assert.ok(Number.isFinite(p.velocidade) && p.velocidade <= VELOCIDADE_MAX_PX_SEG);
});

test('posição: espera no topo, rola, trava no fim', () => {
  const p = planoRolagem({ alturaConteudo: 1900, alturaViewport: 900, duracaoSeg: 30 });
  assert.equal(posicaoRolagem(p, 0), 0);
  assert.equal(posicaoRolagem(p, PAUSA_ROLAGEM_SEG), 0);
  perto(posicaoRolagem(p, PAUSA_ROLAGEM_SEG + 10), 10 * p.velocidade);
  assert.equal(posicaoRolagem(p, 29), 1000);
});

test('índices circulares', () => {
  assert.equal(proximoIndice(0, 3), 1);
  assert.equal(proximoIndice(2, 3), 0);
  assert.equal(anteriorIndice(0, 3), 2);
  assert.equal(anteriorIndice(2, 3), 1);
  assert.equal(proximoIndice(0, 0), 0);
  assert.equal(anteriorIndice(0, 0), 0);
  assert.equal(proximoIndice(0, 1), 0);
});

test('precisaAtualizar respeita o intervalo', () => {
  assert.equal(precisaAtualizar(0, 299_000, 300), false);
  assert.equal(precisaAtualizar(0, 300_000, 300), true);
});

test('filtrosEfetivos: tokens resolvidos na data de agora, override vence', () => {
  const dia8 = new Date(2026, 9, 8), dia9 = new Date(2026, 9, 9);
  const raw = { data: 'hoje', setor: 'Lavoura' };
  assert.deepEqual(filtrosEfetivos(raw, {}, dia8), { data: '2026-10-08', setor: 'Lavoura' });
  assert.deepEqual(filtrosEfetivos(raw, {}, dia9), { data: '2026-10-09', setor: 'Lavoura' });
  assert.deepEqual(filtrosEfetivos(raw, { setor: 'Sede' }, dia8), { data: '2026-10-08', setor: 'Sede' });
  assert.deepEqual(filtrosEfetivos(raw, undefined, dia8), { data: '2026-10-08', setor: 'Lavoura' });
});
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `cd frontend && node --test src/lib/apresentacao.test.js`
Expected: FAIL (módulo não existe).

- [ ] **Step 7: Implementar `apresentacao.js`**

```js
import { resolverFiltros } from './filtrosPainel.js';

export const PAUSA_ROLAGEM_SEG = 3;          // parada no topo e no fim do slide
export const VELOCIDADE_MAX_PX_SEG = 80;     // teto pra manter legível
export const RENOVAR_TOKEN_MS = 30 * 60 * 1000;

// Plano de rolagem de um slide. `duracaoSeg` é o MÍNIMO: se a rolagem (limitada
// ao teto de velocidade) não couber, o slide se estende até o fim da rolagem.
export function planoRolagem({ alturaConteudo, alturaViewport, duracaoSeg }) {
  const distancia = Math.max(0, alturaConteudo - alturaViewport);
  if (distancia < 2) {
    return { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: duracaoSeg };
  }
  const disponivel = Math.max(duracaoSeg - 2 * PAUSA_ROLAGEM_SEG, 1);
  const velocidade = Math.min(distancia / disponivel, VELOCIDADE_MAX_PX_SEG);
  const duracaoRolagemSeg = distancia / velocidade;
  return {
    rola: true,
    distancia,
    velocidade,
    duracaoRolagemSeg,
    tempoTotalSeg: Math.max(duracaoSeg, duracaoRolagemSeg + 2 * PAUSA_ROLAGEM_SEG),
  };
}

export function posicaoRolagem(plano, decorridoSeg) {
  if (!plano.rola) return 0;
  const t = decorridoSeg - PAUSA_ROLAGEM_SEG;
  if (t <= 0) return 0;
  return Math.min(plano.distancia, t * plano.velocidade);
}

export const proximoIndice  = (atual, total) => (total <= 0 ? 0 : (atual + 1) % total);
export const anteriorIndice = (atual, total) => (total <= 0 ? 0 : (atual - 1 + total) % total);

export const precisaAtualizar = (ultimaMs, agoraMs, intervaloSeg) => agoraMs - ultimaMs >= intervaloSeg * 1000;

// Filtros usados na consulta: tokens do slide resolvidos AGORA + o que o usuário editou.
export function filtrosEfetivos(raw, override, agora = new Date()) {
  return { ...resolverFiltros(raw, agora), ...(override ?? {}) };
}
```

- [ ] **Step 8: Rodar tudo e ver passar**

Run: `cd frontend && node --test src/lib/`
Expected: PASS (incluindo os testes antigos `tabelaDinamica.test.js` e `relatorioLimites.test.js`).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/filtrosPainel.js frontend/src/lib/filtrosPainel.test.js frontend/src/lib/apresentacao.js frontend/src/lib/apresentacao.test.js
git commit -m "feat: logica pura de tokens de filtro e plano de rolagem da apresentacao"
```

---

### Task 6: Extrair `PainelGrid.svelte` e usar `filtrosPainel.js` na página de painel

Refatoração sem mudança de comportamento: a página de painel deve ficar idêntica.

**Files:**
- Create: `frontend/src/lib/components/PainelGrid.svelte`
- Modify: `frontend/src/routes/painel/[slug]/+page.svelte`

**Interfaces:**
- Produces: `<PainelGrid {painel} {indicadores} {slug} {filtrosAtivos} {filtrosQuery} {urlImpressaoBase} on:filtroClique />`
  - props: `painel` (precisa de `.colunas`), `indicadores` (array do `renderizar`), `slug` (string, vai para `painelSlug` das tabelas), `filtrosAtivos` (obj), `filtrosQuery` (string), `urlImpressaoBase` (string|null).
  - evento `filtroClique` com `detail = { ind, valor }`.

- [ ] **Step 1: Criar `PainelGrid.svelte`**: mover para ele o bloco `<div class="painel-grid">…</div>` (linhas 265-359 da página atual), a função `valoresClicados(ind)`, os imports dos 6 componentes e `assetUrl`, e os estilos `.painel-grid`, `.grid-item`, `.card-titulo`, `.error`, `.muted` e as regras `@media` correspondentes (tablet/mobile/TV: apenas as que tocam `.painel-grid`, `.grid-item`, `.card-titulo`). Script do componente:

```svelte
<script>
  import { createEventDispatcher } from 'svelte';
  import { assetUrl } from '$lib/api.js';
  import KPICard      from '$lib/components/KPICard.svelte';
  import ChartPanel   from '$lib/components/ChartPanel.svelte';
  import DataTable    from '$lib/components/DataTable.svelte';
  import DynamicTable from '$lib/components/DynamicTable.svelte';
  import MapPanel     from '$lib/components/MapPanel.svelte';
  import CardPerfil   from '$lib/components/CardPerfil.svelte';

  export let painel;
  export let indicadores = [];
  export let slug = '';
  export let filtrosAtivos = {};
  export let filtrosQuery = '';
  export let urlImpressaoBase = null;

  const dispatch = createEventDispatcher();

  function valoresClicados(ind) {
    const s = ind.filtro_clique_variavel_slug;
    if (!s) return [];
    const val = filtrosAtivos[s];
    if (!val) return [];
    return ind.filtro_clique_variavel_tipo === 'multiselect' ? String(val).split(',') : [String(val)];
  }
</script>
```

O markup do grid é copiado literalmente, trocando apenas `on:filtroClique={(e) => onFiltroClique(ind, e.detail.valor)}` por `on:filtroClique={(e) => dispatch('filtroClique', { ind, valor: e.detail.valor })}`.

- [ ] **Step 2: Na página de painel**: remover os imports dos 6 componentes (manter `FiltroVariavel`), apagar `resolverToken`, `valoresIniciais` e `valoresClicados`; importar `import { valoresIniciais } from '$lib/filtrosPainel.js'; import PainelGrid from '$lib/components/PainelGrid.svelte';`; chamar `valoresIniciais(variaveis)` onde antes era `valoresIniciais()` (2 lugares: `carregarPainel` e `limparFiltros`); substituir o bloco do grid por:

```svelte
      <PainelGrid
        {painel}
        {indicadores}
        {slug}
        {filtrosAtivos}
        {filtrosQuery}
        {urlImpressaoBase}
        on:filtroClique={(e) => onFiltroClique(e.detail.ind, e.detail.valor)}
      />
```

Remover da página os estilos que migraram (`.painel-grid`, `.grid-item`, `.card-titulo` e suas linhas nos `@media`). Manter `.error`/`.muted` também na página (são usados lá).

- [ ] **Step 3: Checar tipos/compilação**

Run: `cd frontend && npm run check`
Expected: sem erros novos nos arquivos tocados.

- [ ] **Step 4: Verificação manual no navegador** (frontend de dev reiniciado, conforme nota de ambiente): abrir um painel com KPI, gráfico, tabela e `table_dynamic`; confirmar que o layout, os filtros, o clique em gráfico (filtro por clique) e "Abrir PDF" continuam como antes. Se o navegador de teste travar com gráficos, registrar isso explicitamente.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/PainelGrid.svelte "frontend/src/routes/painel/[slug]/+page.svelte"
git commit -m "refactor: extrai PainelGrid e tokens de filtro da pagina de painel"
```

---

### Task 7: `api.js` + menu e layout

**Files:**
- Modify: `frontend/src/lib/api.js`, `frontend/src/routes/+layout.svelte`

**Interfaces:**
- Produces (`api`): `renovarToken()`, `minhasApresentacoes()`, `executarApresentacao(id)`, `listarApresentacoes()`, `buscarApresentacao(id)`, `criarApresentacao(d)`, `atualizarApresentacao(id,d)`, `desativarApresentacao(id)`, `slidesApresentacao(id)`, `salvarSlidesApresentacao(id,d)`, `usuariosApresentacao(id)`, `salvarUsuariosApresentacao(id,d)`.

- [ ] **Step 1: `api.js`** — junto de Auth e dos métodos de painéis:

```js
    renovarToken: () => request('/api/auth/renovar', { method: 'POST' }),

    // Apresentações
    minhasApresentacoes:        ()        => request('/api/apresentacoes/minhas'),
    executarApresentacao:       (id)      => request(`/api/apresentacoes/${id}/executar`),
    listarApresentacoes:        ()        => request('/api/apresentacoes/'),
    buscarApresentacao:         (id)      => request(`/api/apresentacoes/${id}`),
    criarApresentacao:          (d)       => request('/api/apresentacoes/', { method: 'POST', body: JSON.stringify(d) }),
    atualizarApresentacao:      (id, d)   => request(`/api/apresentacoes/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
    desativarApresentacao:      (id)      => request(`/api/apresentacoes/${id}`, { method: 'DELETE' }),
    slidesApresentacao:         (id)      => request(`/api/apresentacoes/${id}/slides`),
    salvarSlidesApresentacao:   (id, d)   => request(`/api/apresentacoes/${id}/slides`, { method: 'PUT', body: JSON.stringify(d) }),
    usuariosApresentacao:       (id)      => request(`/api/apresentacoes/${id}/usuarios`),
    salvarUsuariosApresentacao: (id, d)   => request(`/api/apresentacoes/${id}/usuarios`, { method: 'PUT', body: JSON.stringify(d) }),
```

- [ ] **Step 2: `+layout.svelte`**
  - Em `I`, acrescentar: `tv: \`<rect x="2" y="7" width="20" height="15" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/>\`,` e `play: \`<polygon points="5 3 19 12 5 21 5 3"/>\`,`.
  - `navLinks` ganha, depois de Dashboard: `{ href: '/apresentar', label: 'Apresentar painéis', icon: I.tv },`.
  - `adminLinks` ganha, depois de Painéis: `{ href: '/configuracoes/apresentacoes', label: 'Apresentações', icon: I.play },`.
  - Esconder o link para externos: `$: navVisiveis = navLinks.filter(l => !(isExterno && l.href === '/apresentar'));` e trocar `{#each navLinks as link}` por `{#each navVisiveis as link}`.
  - Rota sem shell (tela cheia): no `{#if PUBLIC_ROUTES… }{:else if $page.url.pathname.startsWith('/relatorio/')}` acrescentar outro ramo `{:else if $page.url.pathname.startsWith('/apresentar/')}<slot />`. A lista `/apresentar` (sem barra final) continua com o shell normal.
  - O `isActive('/apresentar')` já funciona via `startsWith(href + '/')`.

- [ ] **Step 3: Verificar**: `cd frontend && npm run check` sem erros novos; no navegador o item "Apresentar painéis" aparece abaixo de Dashboard (a página ainda dará 404 até a Task 9 — esperado).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/routes/+layout.svelte
git commit -m "feat: menu Apresentar paineis e metodos de API de apresentacoes"
```

---

### Task 8: Cadastro admin (lista + formulário)

**Files:**
- Create: `frontend/src/routes/configuracoes/apresentacoes/+page.svelte`, `frontend/src/routes/configuracoes/apresentacoes/[id]/+page.svelte`

**Interfaces:**
- Consumes: métodos `api.*Apresentacao*` (Task 7), `api.listarPaineis()`, `api.variaveisPainel(id)`, `api.listarUsuarios()`, `api.listarEmpresas()`, `chavesFiltro` (Task 5).
- Rota `/configuracoes/apresentacoes/nova` = criação (o `[id]` recebe `id === 'nova'`).

- [ ] **Step 1: Lista** (`+page.svelte`), no mesmo padrão visual da lista de painéis (copiar estilos `.page`, `.page-header`, `.cards-grid`, `.card`, `.badge`, `.btn-sm`):

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let apresentacoes = [];
  let busca = '';
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try { apresentacoes = await api.listarApresentacoes(); }
    catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  $: filtradas = apresentacoes.filter(a =>
    !busca.trim() || a.nome.toLowerCase().includes(busca.trim().toLowerCase()));

  async function desativar(a) {
    if (!confirm(`Desativar apresentação "${a.nome}"?`)) return;
    try {
      await api.desativarApresentacao(a.id);
      apresentacoes = apresentacoes.map(x => x.id === a.id ? { ...x, ativo: false } : x);
    } catch (e) { alert(e.message); }
  }
</script>

<svelte:head><title>Apresentações — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Apresentações</h2>
    <a href="/configuracoes/apresentacoes/nova" class="btn-primary">+ Nova Apresentação</a>
  </div>

  {#if carregando}<p class="muted">Carregando...</p>
  {:else if erro}<p class="error">{erro}</p>
  {:else if apresentacoes.length === 0}<p class="muted">Nenhuma apresentação cadastrada.</p>
  {:else}
    <div class="filtros"><input type="text" placeholder="Buscar…" bind:value={busca} /></div>
    <div class="cards-grid">
      {#each filtradas as a}
        <div class="card" class:inativo={!a.ativo}>
          <div class="card-top">
            <span class="card-nome">{a.nome}</span>
            <span class="badge" class:ativo={a.ativo}>{a.ativo ? 'Ativa' : 'Inativa'}</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">slug: <code>{a.slug}</code></span>
            <span class="meta-item">{a.total_slides} slide(s) · atualiza a cada {Math.round(a.intervalo_atualizacao_seg / 60)} min</span>
            <span class="meta-item">{a.empresa_id ? `Empresa #${a.empresa_id}` : 'Todas as empresas'}</span>
            {#if a.descricao}<span class="meta-descricao">{a.descricao}</span>{/if}
          </div>
          <div class="card-actions">
            <a href="/apresentar/{a.id}" class="btn-ghost btn-sm" target="_blank">Apresentar</a>
            <a href="/configuracoes/apresentacoes/{a.id}" class="btn-ghost btn-sm">Editar</a>
            {#if a.ativo}<button class="btn-ghost btn-sm danger" on:click={() => desativar(a)}>Desativar</button>{/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
```
(`<style>`: copiar de `configuracoes/paineis/+page.svelte` as regras usadas acima, mais `.filtros input { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; width: 260px; }`.)

- [ ] **Step 2: Formulário** (`[id]/+page.svelte`). Estado e lógica:

```svelte
<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import { chavesFiltro } from '$lib/filtrosPainel.js';

  const idParam = $page.params.id;
  const criando = idParam === 'nova';

  let form = { slug: '', nome: '', descricao: '', empresa_id: null, intervalo_min: 5, ativo: true };
  let slides = [];            // [{ chave, painel_id, duracao_seg, filtros, variaveis, painel_ativo }]
  let paineis = [];
  let empresas = [];
  let usuarios = [];
  let usuariosSelecionados = [];
  let carregando = true, salvando = false, erro = null;
  let proximaChave = 1;

  onMount(async () => {
    try {
      [paineis, empresas, usuarios] = await Promise.all([
        api.listarPaineis(), api.listarEmpresas(), api.listarUsuarios(),
      ]);
      if (!criando) {
        const [a, sl, us] = await Promise.all([
          api.buscarApresentacao(idParam), api.slidesApresentacao(idParam), api.usuariosApresentacao(idParam),
        ]);
        form = { slug: a.slug, nome: a.nome, descricao: a.descricao ?? '', empresa_id: a.empresa_id,
                 intervalo_min: Math.max(0.5, a.intervalo_atualizacao_seg / 60), ativo: a.ativo };
        usuariosSelecionados = us.map(u => u.id);
        slides = await Promise.all(sl.map(async s => ({
          chave: proximaChave++, painel_id: s.painel_id, duracao_seg: s.duracao_seg,
          filtros: { ...s.filtros }, painel_ativo: s.painel_ativo,
          variaveis: await api.variaveisPainel(s.painel_id).catch(() => []),
        })));
      }
    } catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  // Valores padrão do painel (tokens crus) viram os filtros iniciais do slide.
  function filtrosPadrao(variaveis) {
    const f = {};
    for (const v of variaveis) {
      if (v.tipo === 'date_range') {
        f[v.slug + '_inicio'] = v.valor_padrao_inicio || '';
        f[v.slug + '_fim'] = v.valor_padrao_fim || '';
      } else f[v.slug] = v.valor_padrao || '';
    }
    return f;
  }

  async function adicionarSlide() {
    slides = [...slides, { chave: proximaChave++, painel_id: null, duracao_seg: 30, filtros: {}, variaveis: [], painel_ativo: true }];
  }

  async function trocarPainel(s, painelId) {
    s.painel_id = painelId ? Number(painelId) : null;
    s.variaveis = s.painel_id ? await api.variaveisPainel(s.painel_id).catch(() => []) : [];
    s.filtros = filtrosPadrao(s.variaveis);
    slides = slides;
  }

  function mover(i, delta) {
    const j = i + delta;
    if (j < 0 || j >= slides.length) return;
    const c = [...slides]; [c[i], c[j]] = [c[j], c[i]]; slides = c;
  }

  const remover = (i) => { slides = slides.filter((_, k) => k !== i); };
  function toggleUsuario(uid) {
    usuariosSelecionados = usuariosSelecionados.includes(uid)
      ? usuariosSelecionados.filter(x => x !== uid) : [...usuariosSelecionados, uid];
  }

  async function salvar() {
    erro = null;
    if (!form.nome.trim() || !form.slug.trim()) { erro = 'Informe nome e slug.'; return; }
    if (slides.some(s => !s.painel_id)) { erro = 'Escolha o painel de todos os slides (ou remova o slide vazio).'; return; }
    salvando = true;
    try {
      const corpo = {
        slug: form.slug.trim(), nome: form.nome.trim(), descricao: form.descricao || null,
        empresa_id: form.empresa_id || null,
        intervalo_atualizacao_seg: Math.round(Number(form.intervalo_min) * 60), ativo: form.ativo,
      };
      const id = criando ? (await api.criarApresentacao(corpo)).id : idParam;
      if (!criando) await api.atualizarApresentacao(id, corpo);
      await api.salvarSlidesApresentacao(id, slides.map(s => ({
        painel_id: s.painel_id, duracao_seg: Number(s.duracao_seg), filtros: s.filtros })));
      await api.salvarUsuariosApresentacao(id, usuariosSelecionados);
      goto('/configuracoes/apresentacoes');
    } catch (e) { erro = e.message; }
    finally { salvando = false; }
  }
</script>
```

Markup (3 blocos num `.form-card` cada; reaproveitar classes `.field`, `.section-title`, `.check-label`, `.access-row`, `.badge`, `.hint` copiando os estilos de `configuracoes/paineis/[id]/+page.svelte`):
  1. **Dados**: inputs `nome`, `slug` (com `on:input` que força minúsculas e troca `-`/espaço por `_`), `descricao`, select de `empresa_id` (opção "Todas as empresas" = null), `intervalo_min` (number, min 0.5, step 0.5, rótulo "Atualizar dados a cada (minutos)"), checkbox `ativo`.
  2. **Slides**: `{#each slides as s, i (s.chave)}` com: título "Slide {i+1}", select de painel (`on:change={(e) => trocarPainel(s, e.target.value)}`, opções = `paineis.filter(p => p.ativo || p.id === s.painel_id)`), `duracao_seg` (number, min 5, rótulo "Tempo na tela (segundos)"), aviso `{#if s.painel_id && !s.painel_ativo}<span class="aviso">Painel inativo: será pulado na apresentação</span>{/if}`, e para cada variável `{#each s.variaveis as v}{#each chavesFiltro(v) as c}` um `<label>{c.rotulo}</label><input type="text" bind:value={s.filtros[c.chave]} placeholder="valor ou token (hoje, mes_atual_inicio…)" />`, botões ↑ ↓ ✕ (`mover(i,-1)`, `mover(i,1)`, `remover(i)`) e, ao final, "+ Adicionar slide". Dica com a lista de tokens (mesma frase da tela de painéis).
  3. **Usuários com acesso**: checkboxes iguais ao bloco "Usuários com Acesso" da tela de painéis, com a observação "Administradores sempre enxergam todas as apresentações da empresa."
  - Rodapé: `Cancelar` (link para a lista) e `Salvar` (`disabled={salvando}`); `{#if erro}<p class="error">{erro}</p>{/if}`.

- [ ] **Step 3: Verificar**: `npm run check`; no navegador: criar apresentação com 2 slides (painéis diferentes, um filtro com token `hoje`), salvar, reabrir e conferir que ordem, tempos, filtros e usuários persistiram; testar slug com maiúscula/hífen (deve normalizar) e slug duplicado (mensagem de erro 409 visível).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/configuracoes/apresentacoes
git commit -m "feat: cadastro de apresentacoes no admin"
```

---

### Task 9: Lista do usuário (`/apresentar`)

**Files:**
- Create: `frontend/src/routes/apresentar/+page.svelte`

**Interfaces:**
- Consumes: `api.minhasApresentacoes()` → `[{id,slug,nome,descricao,total_slides}]`.

- [ ] **Step 1: Implementar**

```svelte
<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let lista = [];
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try { lista = await api.minhasApresentacoes(); }
    catch (e) { erro = e.message; }
    finally { carregando = false; }
  });
</script>

<svelte:head><title>Apresentar painéis — GPA Analytics</title></svelte:head>

<div class="page">
  <h2>Apresentar painéis</h2>
  <p class="intro">Escolha uma apresentação para exibir em tela cheia.</p>

  {#if carregando}<p class="muted">Carregando...</p>
  {:else if erro}<p class="error">{erro}</p>
  {:else if lista.length === 0}<p class="muted">Nenhuma apresentação disponível para você.</p>
  {:else}
    <div class="cards-grid">
      {#each lista as a}
        <a class="card" href="/apresentar/{a.id}">
          <span class="card-nome">{a.nome}</span>
          {#if a.descricao}<span class="meta">{a.descricao}</span>{/if}
          <span class="meta">{a.total_slides} slide(s)</span>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.intro { color: var(--muted); font-size: 13px; margin: 4px 0 20px; }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.card { display: flex; flex-direction: column; gap: 6px; padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; text-decoration: none; }
.card:hover { border-color: var(--accent); }
.card-nome { font-size: 15px; font-weight: 600; color: var(--text); }
.meta { font-size: 12px; color: var(--muted); }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

- [ ] **Step 2: Verificar no navegador**: logado como admin e como usuário comum vinculado, a lista mostra o que deveria (usuário sem vínculo vê "Nenhuma apresentação disponível para você").

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/apresentar/+page.svelte
git commit -m "feat: lista de apresentacoes para o usuario"
```

---

### Task 10: Preparo + player em tela cheia

**Files:**
- Create: `frontend/src/lib/components/ApresentacaoPlayer.svelte`, `frontend/src/routes/apresentar/[id]/+page.svelte`

**Interfaces:**
- Consumes: `api.executarApresentacao`, `api.variaveisPainel`, `api.renderizarPainel`, `api.renovarToken`; `PainelGrid`, `FiltroVariavel` (evento `mudou` com `detail` = objeto de chaves/valores); funções de `apresentacao.js` e `filtrosEfetivos`; store `token` de `$lib/stores/auth.js`.
- Produces: `<ApresentacaoPlayer {apresentacao} bind:slides on:sair />` onde `slides = [{id, duracao_seg, filtros, override:{}, variaveis:[], painel:{id,slug,nome,colunas}}]` e `apresentacao = {nome, intervalo_atualizacao_seg}`.

- [ ] **Step 1: Página `[id]/+page.svelte`** (carrega, mostra o preparo e troca para o player):

```svelte
<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
  import ApresentacaoPlayer from '$lib/components/ApresentacaoPlayer.svelte';
  import { filtrosEfetivos } from '$lib/apresentacao.js';

  const id = $page.params.id;
  let apresentacao = null;
  let slides = [];
  let rodando = false;
  let carregando = true;
  let erro = null;

  onMount(async () => {
    try {
      const a = await api.executarApresentacao(id);
      apresentacao = a;
      slides = await Promise.all(a.slides.map(async s => ({
        ...s, override: {}, variaveis: await api.variaveisPainel(s.painel.id).catch(() => []),
      })));
    } catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  async function iniciar() {
    try { await document.documentElement.requestFullscreen?.(); } catch { /* segue sem tela cheia */ }
    rodando = true;
  }

  async function sair() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); } catch { /* ignora */ }
    goto('/apresentar');
  }

  function onMudou(slide, detail) {
    slide.override = { ...slide.override, ...detail };
    slides = slides;
  }
</script>

<svelte:head><title>{apresentacao?.nome ?? 'Apresentação'} — GPA Analytics</title></svelte:head>

{#if rodando}
  <ApresentacaoPlayer {apresentacao} bind:slides on:sair={sair} />
{:else}
  <div class="preparo">
    {#if carregando}<p class="muted">Carregando...</p>
    {:else if erro}<p class="error">{erro}</p><a href="/apresentar" class="btn-ghost">Voltar</a>
    {:else}
      <h2>{apresentacao.nome}</h2>
      {#if apresentacao.descricao}<p class="muted">{apresentacao.descricao}</p>{/if}
      <p class="hint">Ajuste os filtros se quiser (vale só para esta execução) e clique em Iniciar. Os dados são atualizados a cada {Math.round(apresentacao.intervalo_atualizacao_seg / 60)} min.</p>

      {#if slides.length === 0}
        <p class="muted">Nenhum slide cadastrado.</p>
      {:else}
        {#each slides as s, i}
          <div class="slide-card">
            <div class="slide-titulo">Slide {i + 1} — {s.painel.nome} <span class="muted">({s.duracao_seg}s)</span></div>
            {#if s.variaveis.length > 0}
              <div class="filtros-bar">
                {#each s.variaveis as v}
                  <FiltroVariavel variavel={v} valor={filtrosEfetivos(s.filtros, s.override)} on:mudou={(e) => onMudou(s, e.detail)} />
                {/each}
              </div>
            {:else}<span class="muted">Sem filtros.</span>{/if}
          </div>
        {/each}
      {/if}

      <div class="acoes">
        <a href="/apresentar" class="btn-ghost">Voltar</a>
        <button class="btn-primary" on:click={iniciar} disabled={slides.length === 0}>▶ Iniciar apresentação</button>
      </div>
    {/if}
  </div>
{/if}

<style>
.preparo { padding: 24px; max-width: 960px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.hint, .muted { color: var(--muted); font-size: 13px; }
.slide-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-top: 12px; }
.slide-titulo { font-weight: 600; color: var(--text); margin-bottom: 10px; }
.filtros-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.acoes { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
```

(O layout aplica o shell só em `/apresentar` sem id; em `/apresentar/[id]` renderiza só o slot — por isso o preparo também aparece sem menu lateral; tudo bem. Se o tema `data-theme` não for aplicado nessa rota, confirmar no navegador; o bloco reativo do layout já cobre qualquer rota fora de `/relatorio/`.)

- [ ] **Step 2: `ApresentacaoPlayer.svelte`**

```svelte
<script>
  import { onMount, onDestroy, createEventDispatcher, tick } from 'svelte';
  import { api } from '$lib/api.js';
  import { token } from '$lib/stores/auth.js';
  import PainelGrid from '$lib/components/PainelGrid.svelte';
  import FiltroVariavel from '$lib/components/FiltroVariavel.svelte';
  import {
    planoRolagem, posicaoRolagem, proximoIndice, anteriorIndice,
    precisaAtualizar, filtrosEfetivos, RENOVAR_TOKEN_MS,
  } from '$lib/apresentacao.js';

  export let apresentacao;
  export let slides;
  const dispatch = createEventDispatcher();

  let indice = 0;
  let dados = {};                 // { [slideId]: { indicadores, urlImpressaoBase, atualizadoEm } }
  let avisoAtualizacao = null;    // string | null
  let pausado = false;
  let filtrosAbertos = false;
  let controlesVisiveis = false;
  let viewport, conteudo;
  let plano = { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: 30 };
  let decorrido = 0;
  let raf, ultimoFrame = 0;
  let timerAtualizar, timerToken, timerControles, observador, wakeLock;

  $: slide = slides[indice];
  $: dadosSlide = slide ? dados[slide.id] : null;
  $: parado = pausado || filtrosAbertos;
  $: filtrosVigentes = slide ? filtrosEfetivos(slide.filtros, slide.override) : {};
  $: filtrosQuery = new URLSearchParams(filtrosVigentes).toString();

  const hora = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  async function carregar(s) {
    try {
      const r = await api.renderizarPainel(s.painel.id, filtrosEfetivos(s.filtros, s.override));
      dados = { ...dados, [s.id]: { indicadores: r.indicadores, urlImpressaoBase: r.url_impressao_base, atualizadoEm: Date.now() } };
      avisoAtualizacao = null;
    } catch (e) {
      // mantém o que já está na tela; só avisa
      avisoAtualizacao = `Sem atualizar desde ${dados[s.id] ? new Date(dados[s.id].atualizadoEm).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : hora()}`;
    }
  }

  function recalcularPlano() {
    if (!viewport || !slide) return;
    const novo = planoRolagem({
      alturaConteudo: viewport.scrollHeight, alturaViewport: viewport.clientHeight, duracaoSeg: slide.duracao_seg,
    });
    // evita "pulo" por variações mínimas de altura durante a rolagem
    if (novo.rola === plano.rola && Math.abs(novo.distancia - plano.distancia) < 4) return;
    plano = novo;
  }

  async function irPara(novo) {
    indice = novo;
    decorrido = 0;
    await tick();
    if (viewport) viewport.scrollTop = 0;
    plano = { rola: false, distancia: 0, velocidade: 0, duracaoRolagemSeg: 0, tempoTotalSeg: slide?.duracao_seg ?? 30 };
    recalcularPlano();
    const d = dados[slide.id];
    if (!d || precisaAtualizar(d.atualizadoEm, Date.now(), apresentacao.intervalo_atualizacao_seg)) carregar(slide);
  }

  const avancar = () => irPara(proximoIndice(indice, slides.length));
  const voltar  = () => irPara(anteriorIndice(indice, slides.length));

  function quadro(agora) {
    raf = requestAnimationFrame(quadro);
    const dt = ultimoFrame ? (agora - ultimoFrame) / 1000 : 0;
    ultimoFrame = agora;
    if (parado || !slide) return;
    decorrido += dt;
    if (viewport) viewport.scrollTop = posicaoRolagem(plano, decorrido);
    if (decorrido >= plano.tempoTotalSeg) avancar();
  }

  function mostrarControles() {
    controlesVisiveis = true;
    clearTimeout(timerControles);
    timerControles = setTimeout(() => { if (!filtrosAbertos) controlesVisiveis = false; }, 4000);
  }

  async function aplicarFiltros() {
    filtrosAbertos = false;
    await carregar(slide);
  }

  function restaurarFiltros() { slide.override = {}; slides = slides; }

  onMount(async () => {
    if (slides.length === 0) return;
    await carregar(slides[0]);
    await irPara(0);
    observador = new ResizeObserver(recalcularPlano);
    observador.observe(conteudo);
    raf = requestAnimationFrame(quadro);
    // recarrega o slide em exibição no intervalo configurado
    timerAtualizar = setInterval(() => slide && carregar(slide), apresentacao.intervalo_atualizacao_seg * 1000);
    // renova o token pra TV não cair em "sessão expirada"
    timerToken = setInterval(async () => {
      try { token.set((await api.renovarToken()).token); }
      catch (e) { console.error('Falha ao renovar token:', e); }
    }, RENOVAR_TOKEN_MS);
    try { wakeLock = await navigator.wakeLock?.request('screen'); } catch { /* sem wake lock, segue */ }
  });

  onDestroy(() => {
    if (typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(raf);
    clearInterval(timerAtualizar); clearInterval(timerToken); clearTimeout(timerControles);
    observador?.disconnect();
    try { wakeLock?.release(); } catch { /* ignora */ }
  });
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="player" class:sem-cursor={!controlesVisiveis} on:mousemove={mostrarControles} on:touchstart={mostrarControles}>
  {#if slides.length === 0}
    <p class="vazio">Nenhum slide cadastrado.</p>
  {:else}
    <div class="topo">
      <span class="topo-titulo">{slide?.painel.nome}</span>
      <span class="topo-info">
        {#if avisoAtualizacao}<span class="aviso">{avisoAtualizacao}</span>{/if}
        Slide {indice + 1} de {slides.length}{pausado ? ' · pausado' : ''}
      </span>
    </div>

    <div class="viewport" bind:this={viewport}>
      <div class="conteudo" bind:this={conteudo}>
        {#if dadosSlide}
          <PainelGrid
            painel={slide.painel}
            indicadores={dadosSlide.indicadores}
            slug={slide.painel.slug}
            filtrosAtivos={filtrosVigentes}
            {filtrosQuery}
            urlImpressaoBase={dadosSlide.urlImpressaoBase}
          />
        {:else}
          <p class="vazio">{avisoAtualizacao ?? 'Carregando…'}</p>
        {/if}
      </div>
    </div>
  {/if}

  <div class="controles" class:visivel={controlesVisiveis || filtrosAbertos}>
    {#if filtrosAbertos && slide}
      <div class="painel-filtros">
        {#each slide.variaveis as v}
          <FiltroVariavel variavel={v} valor={filtrosVigentes}
            on:mudou={(e) => { slide.override = { ...slide.override, ...e.detail }; slides = slides; }} />
        {:else}<span class="muted">Este painel não tem filtros.</span>{/each}
        <div class="acoes-filtros">
          <button class="btn-ghost" on:click={restaurarFiltros}>Restaurar padrão</button>
          <button class="btn-primary" on:click={aplicarFiltros}>Aplicar</button>
        </div>
      </div>
    {/if}
    <div class="barra">
      <button class="btn-ghost" on:click={voltar} title="Slide anterior">‹</button>
      <button class="btn-ghost" on:click={() => pausado = !pausado}>{pausado ? '▶ Continuar' : '⏸ Pausar'}</button>
      <button class="btn-ghost" on:click={avancar} title="Próximo slide">›</button>
      <button class="btn-ghost" on:click={() => filtrosAbertos = !filtrosAbertos}>Filtros</button>
      <button class="btn-ghost danger" on:click={() => dispatch('sair')}>Sair</button>
    </div>
  </div>
</div>

<style>
.player { position: fixed; inset: 0; background: var(--bg); display: flex; flex-direction: column; z-index: 50; }
.sem-cursor { cursor: none; }
.topo { display: flex; justify-content: space-between; align-items: baseline; padding: 10px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.topo-titulo { font-family: var(--font-display); font-size: 18px; color: var(--text); }
.topo-info { font-size: 13px; color: var(--muted); display: flex; gap: 12px; }
.aviso { color: var(--accent-orange); }
.viewport { flex: 1; overflow: hidden; padding: 16px 24px; }
.vazio { padding: 48px; text-align: center; color: var(--muted); font-size: 18px; }
.controles { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; opacity: 0; pointer-events: none; transition: opacity .25s; z-index: 60; }
.controles.visivel { opacity: 1; pointer-events: auto; }
.barra { display: flex; gap: 6px; padding: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,.35); }
.painel-filtros { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; max-width: min(720px, 92vw); padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,.35); }
.acoes-filtros { display: flex; gap: 8px; margin-left: auto; }
.danger { color: var(--danger, #f85149); }
.muted { color: var(--muted); font-size: 13px; }
@media (min-width: 1920px) { .viewport { padding: 24px 36px; } .topo-titulo { font-size: 26px; } .topo-info { font-size: 16px; } }
</style>
```

Observações para quem implementa: `ResizeObserver`/`requestAnimationFrame` só existem no navegador — todo uso está dentro de `onMount`/handlers, nunca no escopo do módulo (SSR). `slide.override = …; slides = slides;` força a reatividade do Svelte 4 em mutações aninhadas.

- [ ] **Step 3: Checar** `cd frontend && npm run check` (sem erros novos).

- [ ] **Step 4: Verificação manual no navegador (checklist; cada item deve ser marcado ou o motivo da falha registrado)**
  - Preparo: lista os slides com filtros; editar um filtro e iniciar usa o valor editado.
  - Iniciar entra em tela cheia; menu lateral/cabeçalho não aparecem.
  - Slide curto fica exatamente `duracao_seg` e passa para o próximo; do último volta ao primeiro.
  - Slide alto (painel com `table_dynamic` longo): espera ~3 s no topo, rola suave até o fim, espera ~3 s e avança; com conteúdo gigante o slide fica mais que `duracao_seg`.
  - Com `intervalo_atualizacao_seg` = 30 (ajustar no cadastro), a Network mostra `renderizar` repetindo a cada 30 s sem piscar a tela nem voltar a rolagem ao topo.
  - Derrubar o backend por 1 ciclo: dados antigos permanecem + aviso "Sem atualizar desde HH:MM"; religar e o aviso some no ciclo seguinte; não redireciona para login.
  - Mexer o mouse mostra a barra; ela some após ~4 s; Pausar congela troca e rolagem; ‹ › navegam; Filtros abre painel, Aplicar recarrega só aquele slide, Restaurar padrão limpa os overrides; Sair volta para `/apresentar` e sai da tela cheia.
  - Renovação: reduzir temporariamente `RENOVAR_TOKEN_MS` para 10 s, ver `POST /api/auth/renovar` na Network e o `token` do localStorage mudar; **reverter para 30 min antes de commitar**.
  - Se o navegador de teste travar com gráficos/modal, registrar quais itens não puderam ser verificados.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/ApresentacaoPlayer.svelte "frontend/src/routes/apresentar/[id]/+page.svelte"
git commit -m "feat: tela de preparo e player em tela cheia das apresentacoes"
```

---

### Task 11: Documentação, spec e fechamento

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-08-apresentacao-paineis-design.md`

- [ ] **Step 1: Corrigir a spec** nos cinco pontos listados em "Ajustes sobre a spec" (topo deste plano): remover a menção a mudar a checagem de acesso do `renderizar` (seções 1 e "Casos de borda"), registrar externos sem acesso, admin com visão total, filtros com tokens crus + override, e "teto" no lugar de "piso" de velocidade.

- [ ] **Step 2: README** — nova seção curta "Apresentação de painéis (TV)": o que é, onde cadastrar (Admin → Apresentações), como executar (menu → Apresentar painéis → Iniciar), regras (tempo mínimo por slide, rolagem automática, atualização periódica, filtros com tokens), e o deploy: aplicar `scripts/migrations/2026-10-08-apresentacoes.sql` **antes** de publicar o código (como nos deltas anteriores).

- [ ] **Step 3: Suites completas**

Run: `cd backend && python -m pytest tests/ -q` e `cd frontend && node --test src/lib/`
Expected: tudo verde (se algum teste antigo falhar por motivo alheio a esta feature, reportar sem mascarar).

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-08-apresentacao-paineis-design.md
git commit -m "docs: README e spec ajustados da apresentacao de paineis"
```

- [ ] **Step 5: Deploy (só com autorização explícita do usuário — push e produção não fazem parte da execução automática)**: push → aplicar o delta em prod e teste → deploy no EasyPanel → validar com uma apresentação real numa TV por algumas horas (incluindo a renovação do token).

---

## Self-Review

- **Cobertura da spec:** tabelas/API (Tasks 1–4); menu e rota sem shell (7); preparo, tela cheia, troca, rolagem, atualização, falhas, controles, token, wake lock (10); lista do usuário (9); cadastro com 3 blocos, slides inativos sinalizados, vazio, slug `_` (8, 10); extração do grid (6); testes backend/front (2–5); deploy/README (11). Wake lock é uma adição pequena não listada na spec (útil para TV), explicitada na Task 10.
- **Placeholders:** nenhum "TBD"; a única parte descrita sem código literal é o markup/CSS do formulário admin (Task 8) e a cópia mecânica do grid (Task 6), ambas com origem exata indicada e todas as regras de comportamento/estado escritas.
- **Consistência de nomes:** `planoRolagem`/`posicaoRolagem`/`filtrosEfetivos`/`RENOVAR_TOKEN_MS` (Task 5) usados com a mesma assinatura na Task 10; `chavesFiltro` (5) usado na 8; métodos `api.*Apresentacao*` (7) usados em 8, 9, 10; `SlideInput`/`ApresentacaoInput` (2) coerentes com payloads da Task 8; `hard_delete_apresentacao` (2) usado nas fixtures.
