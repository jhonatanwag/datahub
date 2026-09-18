from groq import AsyncGroq
from config.settings import settings

client = AsyncGroq(api_key=settings.GROQ_API_KEY)


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

    extra_kwargs = {"tools": tools, "tool_choice": "auto"} if tools else {}

    for _ in range(5):
        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            max_tokens=1000,
            messages=messages,
            **extra_kwargs,
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


async def transcrever(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    response = await client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-large-v3",
        language="pt",
    )
    return response.text.strip()
