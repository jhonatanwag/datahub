"""Motor de execução de queries dinâmicas com cache e validação SQL."""
import json
from config.databases import query_meta, query_company
from services.cache import cache_get, cache_set

PALAVRAS_PROIBIDAS = [
    'drop', 'truncate', 'delete', 'insert', 'update',
    'alter', 'create', 'grant', 'revoke', 'pg_', 'information_schema'
]


def validar_sql(sql: str) -> bool:
    sql_lower = sql.lower().strip()
    if not sql_lower.startswith('select'):
        raise ValueError("Apenas queries SELECT são permitidas")
    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in sql_lower:
            raise ValueError(f"Palavra não permitida: '{palavra}'")
    return True


async def resolver_query(
    slug: str,
    company_slug: str,
    empresa_id: int,
    parametros: dict = None
) -> dict:
    if parametros is None:
        parametros = {}
    rows = await query_meta("""
        SELECT q.*
        FROM queries q
        WHERE q.slug = $1
          AND q.ativo = true
          AND (q.empresa_id = $2 OR q.empresa_id IS NULL)
        ORDER BY q.empresa_id NULLS LAST
        LIMIT 1
    """, slug, empresa_id)

    if not rows:
        raise ValueError(f"Query '{slug}' não encontrada ou inativa")

    query = dict(rows[0])

    params_key = json.dumps(parametros, sort_keys=True)
    cache_key = f"query:{slug}:{company_slug}:{params_key}"

    if query["cache_ttl"] > 0:
        cached = await cache_get(cache_key)
        if cached:
            return {"data": cached, "from_cache": True, "query": query["nome"], "tipo": query["tipo"]}

    sql = query["sql_texto"]

    param_rows = await query_meta(
        "SELECT * FROM query_parametros WHERE query_id = $1 ORDER BY id",
        query["id"]
    )

    valores = []
    for p in param_rows:
        val = parametros.get(p["nome"], p["valor_padrao"])
        if val is None and p["obrigatorio"]:
            raise ValueError(f"Parâmetro obrigatório ausente: {p['nome']}")
        valores.append(val)

    resultado = await query_company(company_slug, sql, *valores)
    data = [dict(r) for r in resultado]

    if query["cache_ttl"] > 0:
        await cache_set(cache_key, data, ttl=query["cache_ttl"])

    return {
        "data": data,
        "from_cache": False,
        "query": query["nome"],
        "tipo": query["tipo"]
    }


async def invalidar_cache_empresa(company_slug: str):
    from config.redis import get_redis
    redis = await get_redis()
    keys = await redis.keys(f"query:*:{company_slug}:*")
    if keys:
        await redis.delete(*keys)
