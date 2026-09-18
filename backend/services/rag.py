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
