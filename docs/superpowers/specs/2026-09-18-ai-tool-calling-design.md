# Chat IA — tool-calling pra queries `rag_context` — Design

## Contexto

Hoje `services/rag.py:build_context()` busca **todas** as queries `tipo =
'rag_context'` ativas (globais + da empresa) e executa **todas elas**, toda
vez que o usuário manda qualquer mensagem no chat — mesmo que a pergunta só
precise de um domínio. O resultado vira uma string gigante concatenada no
`system_prompt` (`services/groq_client.py:ask()`).

Isso já mostrou dois problemas reais nesta sessão, com só 2 queries
`rag_context` cadastradas:
- Confundir contexto de empresas diferentes exige limpar cache manualmente
  em mais de um lugar (`rag_context:{empresa}` em `ai.py` + o cache próprio
  de cada query em `resolver_query`).
- Uma única query rica (`rag_contexto_abastecimento`, dado real da
  `vitoria-agronegocios`) chegou perto sozinha do limite de 8.000
  tokens/minuto da conta Groq (tier `on_demand`). Com 10 queries `rag_context`
  cadastradas (o motivador desta mudança), mandar tudo sempre estouraria
  esse limite em qualquer pergunta, mesmo as mais simples ("oi").

**Decisão confirmada com o usuário:** trocar "manda tudo sempre" por
**tool-calling** — cada query `rag_context` vira uma função que o modelo
decide chamar (ou não) conforme o assunto da pergunta. Validado nesta sessão
que o modelo atual (`openai/gpt-oss-120b`) chama a ferramenta certa sozinho,
sem nenhuma instrução extra sobre qual assunto ela cobre além da própria
descrição da ferramenta.

## Decisões

- **Nenhuma mudança de schema.** `queries.slug` vira o nome da função (já
  são identificadores válidos: minúsculo, `_`, sem espaço — testado com
  `rag_contexto_abastecimento`). `queries.nome`/`descricao` viram o rótulo/
  descrição da ferramenta que o modelo lê pra decidir se deve chamar.
- **Ferramentas sem parâmetro.** Toda query `rag_context` hoje já é
  self-contained (sem `query_parametros` obrigatórios, filtros de data
  fixos no próprio SQL — ver `PROMPT-CRIAR-DASHBOARDS.md`). Cada ferramenta
  é declarada com `parameters: {type: object, properties: {}}` — o modelo só
  decide **se** chama, não **com o quê**. Simplifica o loop (não precisa
  validar/mapear argumentos vindos do modelo).
- **Loop de tool-calling com limite de segurança.** Até 5 idas e voltas
  modelo↔ferramentas por pergunta; se passar disso, devolve uma mensagem de
  erro em vez de loopar indefinidamente.
- **Chamadas paralelas do modelo são todas executadas.** Se o modelo pedir
  2+ ferramentas na mesma resposta (ex: pergunta cruza Abastecimento e
  Pendências), executa todas antes de mandar de volta — não força uma por
  vez.
- **Cache por ferramenta, não mais por conversa.** Remove o cache
  `rag_context:{empresa}` (chave única pra todo o contexto). Cada ferramenta,
  quando chamada, passa por `resolver_query()` normalmente — que já cacheia
  por `query:{slug}:{empresa}:{params}` com o `cache_ttl` de cada query. Sai
  ganhando granularidade: editar uma query só invalida ela, não o "contexto"
  inteiro de todo mundo.
- **Erro de ferramenta não derruba a conversa.** Se uma query `rag_context`
  falhar na execução (mesmo padrão que já existia em `build_context`), o
  modelo recebe uma mensagem de erro como resultado da ferramenta e decide o
  que fazer (normalmente relatar que não conseguiu buscar aquele dado) — não
  levanta exceção pro chamador.
- **Sem ferramenta nenhuma disponível** (empresa sem nenhuma `rag_context`
  ativa): não manda `tools` pro Groq (em vez de mandar lista vazia — mais
  seguro contra peculiaridades da API) e o `system_prompt` avisa
  explicitamente que não há fonte de dados configurada, pra não inventar.
- **Frontend não muda.** `AIChat.svelte`/`api.js` continuam chamando
  `POST /api/ai/ask` do mesmo jeito — o loop de tool-calling é inteiramente
  server-side, invisível pro cliente (só o tempo de resposta muda, pode ficar
  um pouco mais alto quando há chamada de ferramenta).
- **`chat_historico` não muda.** Continua guardando só `pergunta`/`resposta`
  finais — o rastro de qual(is) ferramenta(s) foi chamada fica só nos logs
  da requisição, não persiste em banco (fora de escopo; consideração pra uma
  iteração futura se o usuário quiser auditoria).

## Backend

### `backend/services/rag.py` (reescrito)

Sai `build_context()`. Entram duas funções:

```python
"""Ferramentas de tool-calling pro chat IA, uma por query tipo rag_context."""
from config.databases import query_meta
from services.query_runner import resolver_query
import json


async def listar_ferramentas_rag(empresa_id: int) -> list[dict]:
    """Metadado só (slug/nome/descrição) — não executa nenhuma query.
    Mesmo padrão empresa-tem-prioridade-sobre-global de build_context."""
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

### `backend/services/groq_client.py` — `ask()` reescrito

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

`transcrever()` (linha 27-33 atual) não muda.

### `backend/routes/ai.py` — `chatbot()` reescrito

- Trocar import (linha 4-6):
  ```python
  from services.rag import listar_ferramentas_rag, executar_ferramenta_rag
  from services.groq_client import ask, transcrever
  ```
  (remove `from services.cache import cache_get, cache_set, TTL_CHARTS` — não usado por mais nada no arquivo; confirmar antes de remover que `transcrever_audio` não depende disso, o que já é o caso.)
- `chatbot()` (linha 17-38):
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
- `/transcrever` (linha 41-48) e `/historico` (linha 51-63) não mudam.

## Frontend

Nenhuma mudança. `frontend/src/lib/components/AIChat.svelte` e
`frontend/src/lib/api.js` (`perguntarIA`) continuam exatamente como estão.

## Fora de escopo

- Ferramentas com parâmetros (ex: "traga abastecimento só do veículo X") —
  todas as queries `rag_context` de hoje já são self-contained; se um dia
  fizer sentido parametrizar, é um design novo (schema pra declarar quais
  `query_parametros` viram argumentos da função).
- Persistir o rastro de quais ferramentas foram chamadas em
  `chat_historico` (auditoria/debug) — só relatado nos logs da request por
  enquanto.
- Migrar `rag_contexto_principal`/`rag_contexto_abastecimento` pra
  descrições mais "orientadas a ferramenta" (hoje dizem "injetado no
  chatbot", que ainda faz sentido como descrição, só deixou de ser preciso
  tecnicamente) — não bloqueia a função, ajuste cosmético opcional.

## Verificação

- Pergunta só sobre abastecimento (`qual foi o último abastecimento`) →
  só a ferramenta de abastecimento é chamada (confirmar via log/instrumentação
  manual durante o teste), resposta correta.
- Pergunta só sobre o resumo geral (`quantos usuários ativos temos?`) → só
  `rag_contexto_principal` é chamada, não abastecimento.
- Pergunta genérica (`oi`, `quem é você?`) → nenhuma ferramenta chamada,
  resposta ainda sai (mais rápida, menos tokens).
- Pergunta cruzando os dois domínios → confirma que o modelo consegue pedir
  as duas ferramentas (paralelo ou sequencial) e responde combinando os dois.
- Empresa sem nenhuma `rag_context` ativa (se existir alguma de teste) →
  não quebra, responde avisando que não há dado configurado.
- Uma ferramenta que falha (forçar erro, ex: query com SQL quebrado
  temporariamente) → conversa não quebra, modelo relata que não conseguiu
  buscar aquele dado.
- Medir tokens de uma pergunta de 1 domínio só — deve ficar bem abaixo do
  que "mandar tudo sempre" custava (baseline: ~7.250 tokens só pra
  Abastecimento antes desta mudança).
- `GET /api/ai/historico` e `POST /api/ai/transcrever` continuam
  funcionando sem regressão (não tocados, mas fazem parte do mesmo arquivo).
