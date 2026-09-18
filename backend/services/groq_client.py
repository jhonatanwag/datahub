import groq
from groq import AsyncGroq
from config.settings import settings

client = AsyncGroq(api_key=settings.GROQ_API_KEY)


class LimiteTokensError(Exception):
    """Levantado quando a Groq recusa o pedido por estourar o limite de
    tokens/minuto da conta (429 rate_limit_exceeded, ou 413 quando um único
    pedido já é maior que o limite — a Groq usa o mesmo `code` pros dois)."""

    def __init__(self, espere_segundos: int):
        self.espere_segundos = espere_segundos
        super().__init__(f"Limite de tokens da Groq atingido — tente novamente em {espere_segundos}s")


async def _completar(messages: list[dict], extra_kwargs: dict):
    """Chama a Groq e devolve (mensagem, tokens_restantes, tokens_limite).
    Usa with_raw_response pra ter acesso aos headers de rate-limit tanto no
    sucesso (contador) quanto no erro (quanto tempo esperar)."""
    try:
        raw = await client.chat.completions.with_raw_response.create(
            model="openai/gpt-oss-120b",
            max_tokens=1000,
            messages=messages,
            **extra_kwargs,
        )
    except groq.APIStatusError as e:
        codigo = (e.body or {}).get("error", {}).get("code") if isinstance(e.body, dict) else None
        if codigo == "rate_limit_exceeded":
            espere = int(e.response.headers.get("retry-after", "60"))
            raise LimiteTokensError(espere) from e
        raise

    response = await raw.parse()
    tokens_restantes = raw.headers.get("x-ratelimit-remaining-tokens")
    tokens_limite = raw.headers.get("x-ratelimit-limit-tokens")
    return (
        response.choices[0].message,
        int(tokens_restantes) if tokens_restantes is not None else None,
        int(tokens_limite) if tokens_limite is not None else None,
    )


async def ask(question: str, ferramentas: list[dict], executar_ferramenta, company_name: str) -> dict:
    tem_ferramentas = bool(ferramentas)
    system_prompt = f"""Seu nome é Mané. Você é o assistente virtual de analytics de negócios da empresa "{company_name}".
Se alguém perguntar seu nome ou quem é você, responda que é o Mané.
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

    extra_kwargs = {"tools": tools, "tool_choice": "auto"} if tools else {}

    tokens_restantes = tokens_limite = None
    for _ in range(5):
        msg, tokens_restantes, tokens_limite = await _completar(messages, extra_kwargs)
        if not msg.tool_calls:
            return {"resposta": msg.content, "tokens_restantes": tokens_restantes, "tokens_limite": tokens_limite}

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

    return {
        "resposta": "Não consegui concluir a resposta (limite de chamadas de ferramenta atingido).",
        "tokens_restantes": tokens_restantes,
        "tokens_limite": tokens_limite,
    }


async def transcrever(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    response = await client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-large-v3",
        language="pt",
    )
    return response.text.strip()
