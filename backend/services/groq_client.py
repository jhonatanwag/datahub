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
