"""RAG dinâmico: executa queries do tipo rag_context cadastradas no datahub_meta."""
import json
from config.databases import query_meta
from services.query_runner import resolver_query


async def build_context(company_slug: str, empresa_id: int) -> str:
    rag_queries = await query_meta("""
        SELECT DISTINCT ON (slug) slug, nome
        FROM queries
        WHERE tipo = 'rag_context'
          AND ativo = true
          AND (empresa_id = $1 OR empresa_id IS NULL)
        ORDER BY slug, empresa_id NULLS LAST
    """, empresa_id)

    if not rag_queries:
        return "Nenhum contexto de dados configurado para esta empresa."

    partes = []
    for q in rag_queries:
        try:
            resultado = await resolver_query(
                slug=q["slug"],
                company_slug=company_slug,
                empresa_id=empresa_id
            )
            partes.append(
                f"[{q['nome']}]:\n{json.dumps(resultado['data'], default=str, ensure_ascii=False)}"
            )
        except Exception as e:
            partes.append(f"[{q['nome']}]: erro ao buscar dados ({e})")

    return "\n\n".join(partes)
