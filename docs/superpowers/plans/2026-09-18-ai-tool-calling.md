# Chat IA — Tool-Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o chat IA de "manda todas as queries `rag_context` sempre" por tool-calling — o modelo decide quais ferramentas (uma por query `rag_context`) chamar conforme o assunto da pergunta.

**Architecture:** `services/rag.py` expõe metadado das ferramentas (sem executar nada) + uma função de execução sob demanda; `services/groq_client.py` roda o loop modelo↔ferramentas (até 5 rounds); `routes/ai.py` liga as duas pontas. Sem schema novo, sem mudança de frontend.

**Tech Stack:** FastAPI + Groq SDK (`AsyncGroq`, já com suporte a `tools`/`tool_choice` confirmado na versão instalada), modelo `openai/gpt-oss-120b`.

**Spec:** `docs/superpowers/specs/2026-09-18-ai-tool-calling-design.md`

## Global Constraints

- Nenhuma mudança de schema — `queries.slug`/`nome`/`descricao` já servem de nome/descrição de ferramenta.
- Ferramentas sem parâmetro (`parameters: {type: object, properties: {}}`).
- Loop de tool-calling limitado a 5 rounds.
- Erro de ferramenta vira conteúdo de erro pro modelo, nunca exceção pro chamador.
- Frontend (`AIChat.svelte`, `api.js`) não muda.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/services/rag.py` | Reescrito: `listar_ferramentas_rag` (metadado) + `executar_ferramenta_rag` (execução sob demanda) — substitui `build_context` |
| `backend/services/groq_client.py` | `ask()` reescrito com loop de tool-calling; `transcrever()` intacto |
| `backend/routes/ai.py` | `chatbot()` religado às novas funções; import de cache removido |

---

### Task 1: Reescrever `services/rag.py`

**Files:**
- Modify: `backend/services/rag.py` (arquivo inteiro, 35 linhas)

**Interfaces:**
- Produces: `listar_ferramentas_rag(empresa_id: int) -> list[dict]` (cada item `{slug, nome, descricao}`); `executar_ferramenta_rag(slug: str, company_slug: str, empresa_id: int) -> str` (JSON serializado, nunca levanta exceção) — consumidos pela Task 3.

- [ ] **Step 1: Substituir o arquivo inteiro**

```python
"""Ferramentas de tool-calling pro chat IA, uma por query tipo rag_context."""
from config.databases import query_meta
from services.query_runner import resolver_query
import json


async def listar_ferramentas_rag(empresa_id: int) -> list[dict]:
    """Metadado só (slug/nome/descrição) — não executa nenhuma query.
    Mesma prioridade empresa > global que o resto do sistema já usa."""
    rows = await query_meta("""
        SELECT DISTINCT ON (slug) slug, nome, descricao
        FROM queries
        WHERE tipo = 'rag_context'
          AND ativo = true
          AND (empresa_id = $1 OR empresa_id IS NULL)
        ORDER BY slug, empresa_id NULLS LAST
    """, empresa_id)
    return [dict(r) for r in rows]


async def executar_ferramenta_rag(slug: str, company_slug: str, empresa_id: int) -> str:
    """Roda uma query rag_context sob demanda (chamada pelo modelo) e
    devolve o resultado já serializado — nunca levanta exceção, erro vira
    conteúdo de ferramenta pro modelo decidir o que fazer."""
    try:
        resultado = await resolver_query(slug=slug, company_slug=company_slug, empresa_id=empresa_id)
        return json.dumps(resultado["data"], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"erro": f"Não foi possível buscar esse dado: {e}"}, ensure_ascii=False)
```

- [ ] **Step 2: Verificar rapidamente (script ad-hoc, sem framework de teste pra este arquivo hoje)**

```bash
docker exec datahub_backend python -c "
import asyncio
from services.rag import listar_ferramentas_rag, executar_ferramenta_rag

async def main():
    ferramentas = await listar_ferramentas_rag(4)  # vitoria-agronegocios
    for f in ferramentas:
        print(f['slug'], '-', f['nome'])
    if ferramentas:
        r = await executar_ferramenta_rag(ferramentas[0]['slug'], 'vitoria-agronegocios', 4)
        print('exec OK, tamanho:', len(r))

asyncio.run(main())
"
```
Expected: lista as queries `rag_context` ativas (`rag_contexto_principal`, `rag_contexto_abastecimento`) e a execução da primeira devolve uma string JSON não vazia.

- [ ] **Step 3: Commit**

```bash
git add backend/services/rag.py
git commit -m "feat: rag.py vira metadado+execução sob demanda de ferramentas (base do tool-calling)"
```

---

### Task 2: Reescrever `ask()` em `services/groq_client.py`

**Files:**
- Modify: `backend/services/groq_client.py:7-24` (função `ask`)

**Interfaces:**
- Consumes: nada de tasks anteriores diretamente (recebe `ferramentas`/`executar_ferramenta` como parâmetros, decidido pela Task 3).
- Produces: `ask(question: str, ferramentas: list[dict], executar_ferramenta: Callable[[str], Awaitable[str]], company_name: str) -> str`.

- [ ] **Step 1: Substituir a função `ask`**

Trocar linhas 7-24 (a função `ask` inteira) por:

```python
async def ask(question: str, ferramentas: list[dict], executar_ferramenta, company_name: str) -> str:
    tem_ferramentas = bool(ferramentas)
    system_prompt = f"""Você é um assistente de analytics de negócios da empresa "{company_name}".
Responda SEMPRE em português, de forma direta e objetiva (máx 3 parágrafos).
Não invente números — baseie toda resposta numérica em dado real obtido pelas ferramentas.
{"Você tem ferramentas disponíveis pra consultar dados reais da empresa — use a(s) ferramenta(s) relevante(s) pra pergunta antes de responder. Se nenhuma ferramenta tiver o dado necessário, diga isso claramente." if tem_ferramentas else "Não há nenhuma fonte de dados configurada para esta empresa — avise o usuário que você não pode responder com dados reais agora."}"""

    tools = [
        {
            "type": "function",
            "function": {
                "name": f["slug"],
                "description": f["descricao"] or f["nome"],
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for f in ferramentas
    ] or None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    for _ in range(5):
        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            max_tokens=1000,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            resultado = await executar_ferramenta(tc.function.name)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": resultado,
            })

    return "Não consegui concluir a resposta (limite de chamadas de ferramenta atingido)."
```

`transcrever()` (linha 27-33 atual) fica intacta, sem mudança.

- [ ] **Step 2: Verificar isoladamente com uma ferramenta fake (sem depender da Task 3 ainda)**

```bash
docker exec datahub_backend python -c "
import asyncio
from services.groq_client import ask

async def fake_executar(nome):
    return '{\"total_litros\": 999}'

async def main():
    ferramentas = [{'slug': 'dados_abastecimento', 'nome': 'Abastecimento', 'descricao': 'Dados de abastecimento de combustível.'}]
    resposta = await ask('quantos litros de combustível já abastecemos?', ferramentas, fake_executar, 'Teste')
    print(resposta)

asyncio.run(main())
"
```
Expected: a resposta menciona 999 litros (prova que o loop chamou a ferramenta fake e usou o resultado).

- [ ] **Step 3: Commit**

```bash
git add backend/services/groq_client.py
git commit -m "feat: ask() vira loop de tool-calling em vez de contexto fixo"
```

---

### Task 3: Religar `routes/ai.py`

**Files:**
- Modify: `backend/routes/ai.py:1-38`

**Interfaces:**
- Consumes: `listar_ferramentas_rag`, `executar_ferramenta_rag` (Task 1); `ask` com a nova assinatura (Task 2).

- [ ] **Step 1: Trocar os imports (linhas 1-8)**

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from middleware.auth import get_current_user
from services.rag import listar_ferramentas_rag, executar_ferramenta_rag
from services.groq_client import ask, transcrever
from config.databases import query_meta
```

(Remove a linha `from services.cache import cache_get, cache_set, TTL_CHARTS` e o `import json` deixa de ser necessário nesse arquivo — nada mais usa `json` aqui depois da mudança; conferir com uma busca no arquivo antes de remover.)

- [ ] **Step 2: Reescrever `chatbot()` (linhas 17-38)**

```python
@router.post("/ask")
async def chatbot(body: PerguntaInput, user=Depends(get_current_user)):
    try:
        ferramentas = await listar_ferramentas_rag(user["empresa_id"])

        async def executar_ferramenta(nome: str) -> str:
            return await executar_ferramenta_rag(nome, user["company_slug"], user["empresa_id"])

        resposta = await ask(body.pergunta, ferramentas, executar_ferramenta, user["company_name"])

        await query_meta(
            """INSERT INTO chat_historico (usuario_id, empresa_id, pergunta, resposta)
               VALUES ($1, $2, $3, $4)""",
            user["id"], user["empresa_id"], body.pergunta, resposta
        )

        return {"resposta": resposta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no chatbot: {e}")
```

`/transcrever` e `/historico` não mudam.

- [ ] **Step 3: Restart do backend e smoke test da rota real**

```bash
docker restart datahub_backend
```

Depois de subir, testar a rota HTTP real (auth real, igual o frontend chama):

```bash
docker exec datahub_backend sh -c "
TOKEN=\$(curl -s -X POST http://localhost:3001/api/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"admin@datahub.local\",\"senha\":\"admin123\"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"session_token\"])')
JWT=\$(curl -s -X POST http://localhost:3001/api/auth/selecionar-empresa -H 'Content-Type: application/json' -d \"{\\\"session_token\\\":\\\"\$TOKEN\\\",\\\"empresa_id\\\":4}\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"token\"])')
curl -s -X POST http://localhost:3001/api/ai/ask -H \"Authorization: Bearer \$JWT\" -H 'Content-Type: application/json' -d '{\"pergunta\":\"qual foi o ultimo abastecimento\"}'
"
```
Expected: 200, resposta menciona uma data/veículo real (não erro).

- [ ] **Step 4: Verificação completa (cenários do spec)**

Rodar via script Python (mesmo padrão dos testes ad-hoc já usados nesta sessão), contra `vitoria-agronegocios` (empresa_id=4, tem `rag_contexto_abastecimento` com dado real) — pra cada pergunta, confirmar a resposta e, opcionalmente, instrumentar `executar_ferramenta_rag` temporariamente com um `print(slug)` pra ver no log do backend qual ferramenta foi chamada:

1. `"qual foi o último abastecimento"` → só ferramenta de abastecimento.
2. `"quantos usuários ativos temos?"` → só `rag_contexto_principal`.
3. `"oi"` → nenhuma ferramenta chamada.
4. Pergunta cruzando os dois domínios (ex: `"quantos usuários ativos temos e qual foi o total de litros abastecidos?"`) → as duas ferramentas chamadas.

- [ ] **Step 5: Medir tokens de uma pergunta de 1 domínio (comparação com o baseline)**

```bash
docker exec datahub_backend python -c "
import asyncio
from services.rag import listar_ferramentas_rag
from services.groq_client import ask, client

async def main():
    ferramentas = await listar_ferramentas_rag(4)
    # conta querying real: usa response.usage depois da chamada
    import services.groq_client as gc
    orig = gc.client.chat.completions.create
    async def wrapped(*a, **kw):
        r = await orig(*a, **kw)
        print('tokens prompt:', r.usage.prompt_tokens, '/ completion:', r.usage.completion_tokens)
        return r
    gc.client.chat.completions.create = wrapped
    resposta = await ask('qual foi o ultimo abastecimento', ferramentas, lambda n: gc_exec(n), 'Vitória Agronegócios')
    print(resposta)

async def gc_exec(nome):
    from services.rag import executar_ferramenta_rag
    return await executar_ferramenta_rag(nome, 'vitoria-agronegocios', 4)

asyncio.run(main())
"
```
Expected: `tokens prompt` bem abaixo dos ~7.250 tokens que o `rag_contexto_abastecimento` sozinho custava antes (baseline desta sessão) — confirma que perguntas de 1 domínio não carregam mais os outros.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/ai.py
git commit -m "feat: /api/ai/ask usa tool-calling em vez de contexto fixo (ferramenta por domínio rag_context)"
```

---

### Task 4: Verificação final e limpeza

- [ ] **Step 1: Rodar a suíte completa do backend (regressão)**

```bash
docker exec datahub_backend python -m pytest tests/ -v
```
Expected: sem regressão (não há teste automatizado pra `routes/ai.py` hoje — suíte cobre o resto do sistema).

- [ ] **Step 2: Confirmar `/api/ai/historico` e `/api/ai/transcrever` sem regressão**

```bash
docker exec datahub_backend sh -c "curl -s http://localhost:3001/api/health"
```
(smoke test genérico — os dois endpoints não foram tocados nesta mudança, mas fazem parte do mesmo arquivo reescrito)

- [ ] **Step 3: Resumo pro usuário**

Reportar: tokens antes/depois pra pergunta de 1 domínio, confirmação de que perguntas cruzando domínios funcionam, e lembrete de que isso é só backend — nada de frontend ou schema pra levar em produção além do código em si (deploy normal via EasyPanel).
