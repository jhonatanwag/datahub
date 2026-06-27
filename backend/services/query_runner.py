"""Motor de execução de queries dinâmicas com cache e validação SQL."""
import json
import calendar
from datetime import datetime, date as date_type, timedelta
from config.databases import query_meta, query_company
from services.cache import cache_get, cache_set


def _cast(val):
    """
    Normaliza um valor de parâmetro antes de enviar ao asyncpg:
    - None ou string vazia → None  (SQL NULL — cai no valor_padrao do param)
    - Token dinâmico       → datetime.date resolvido no momento da execução
    - String YYYY-MM-DD    → datetime.date
    - Qualquer outro tipo  → retorna como está

    Tokens suportados:
      hoje · ontem
      mes_atual_inicio · mes_atual_fim
      mes_anterior_inicio · mes_anterior_fim
      ano_atual_inicio · ano_atual_fim
    """
    if val is None or val == '':
        return None

    if not isinstance(val, str):
        return val

    hoje = date_type.today()
    ano, mes = hoje.year, hoje.month
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]

    mes_ant = mes - 1 if mes > 1 else 12
    ano_ant = ano if mes > 1 else ano - 1
    ultimo_dia_mes_ant = calendar.monthrange(ano_ant, mes_ant)[1]

    tokens = {
        'hoje':                 hoje,
        'ontem':                hoje - timedelta(days=1),
        'mes_atual_inicio':     date_type(ano, mes, 1),
        'mes_atual_fim':        date_type(ano, mes, ultimo_dia_mes),
        'mes_anterior_inicio':  date_type(ano_ant, mes_ant, 1),
        'mes_anterior_fim':     date_type(ano_ant, mes_ant, ultimo_dia_mes_ant),
        'ano_atual_inicio':     date_type(ano, 1, 1),
        'ano_atual_fim':        date_type(ano, 12, 31),
    }

    if val in tokens:
        return tokens[val]

    if len(val) == 10 and val[4] == '-' and val[7] == '-':
        try:
            return datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            pass

    return val


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

    param_rows = await query_meta("""
        SELECT qp.*, v.slug AS variavel_slug
        FROM query_parametros qp
        LEFT JOIN variaveis v ON v.id = qp.variavel_id
        WHERE qp.query_id = $1
        ORDER BY qp.id
    """, query["id"])

    valores = []
    for p in param_rows:
        variavel_slug = p["variavel_slug"]
        if variavel_slug and p["param_slot"]:
            chave = f"{variavel_slug}_{p['param_slot']}"
        elif variavel_slug:
            chave = variavel_slug
        else:
            chave = p["nome"]

        val = parametros.get(chave)
        # String vazia conta como "não informado" — cai no valor_padrao
        if val is None or val == '':
            val = p["valor_padrao"]

        if val is None and p["obrigatorio"]:
            raise ValueError(f"Parâmetro obrigatório ausente: {chave}")

        valores.append(_cast(val))

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
