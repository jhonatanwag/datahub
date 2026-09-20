from contextlib import asynccontextmanager
import asyncpg
from typing import Dict, Optional
from config.settings import settings

_meta_pool: Optional[asyncpg.Pool] = None
_company_pools: Dict[str, asyncpg.Pool] = {}


async def get_meta_pool() -> asyncpg.Pool:
    global _meta_pool
    if _meta_pool is None:
        _meta_pool = await asyncpg.create_pool(
            host=settings.META_DB_HOST,
            port=settings.META_DB_PORT,
            database=settings.META_DB_NAME,
            user=settings.META_DB_USER,
            password=settings.META_DB_PASS,
            min_size=2,
            max_size=10,
        )
    return _meta_pool


async def get_company_pool(company_slug: str) -> asyncpg.Pool:
    if company_slug in _company_pools:
        return _company_pools[company_slug]

    meta = await get_meta_pool()
    async with meta.acquire() as conn:
        empresa = await conn.fetchrow(
            "SELECT * FROM empresas WHERE slug = $1 AND ativo = true",
            company_slug
        )

    if not empresa:
        raise ValueError(f"Empresa '{company_slug}' não encontrada ou inativa")

    pool = await asyncpg.create_pool(
        host=empresa["db_host"],
        port=empresa["db_port"],
        database=empresa["db_name"],
        user=empresa["db_user"],
        password=empresa["db_pass"],
        min_size=2,
        max_size=10,
    )
    _company_pools[company_slug] = pool
    return pool


async def query_company(company_slug: str, sql: str, *args):
    pool = await get_company_pool(company_slug)
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


class LimiteLinhasError(Exception):
    """A query devolveria mais linhas que `settings.MAX_LINHAS_QUERY`."""


async def query_company_limitado(company_slug: str, sql: str, *args):
    """Como `query_company`, mas lê em cursor só até `MAX_LINHAS_QUERY + 1` linhas: se passar do
    teto, aborta sem materializar o resto (o servidor para de enviar) e levanta LimiteLinhasError."""
    limite = settings.MAX_LINHAS_QUERY
    pool = await get_company_pool(company_slug)
    async with pool.acquire() as conn:
        async with conn.transaction():
            cursor = await conn.cursor(sql, *args)
            linhas = await cursor.fetch(limite + 1)
    if len(linhas) > limite:
        raise LimiteLinhasError(
            f"A consulta retornou mais de {limite:,} linhas".replace(",", ".")
            + ". Refine os filtros (período, ficha, propriedade…) e tente novamente."
        )
    return linhas


async def query_meta(sql: str, *args):
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


@asynccontextmanager
async def meta_tx():
    """Conexão dedicada do pool meta dentro de uma transação — para
    operações multi-tabela que precisam ser atômicas (ex: importação)."""
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


async def close_all_pools():
    global _meta_pool, _company_pools
    if _meta_pool:
        await _meta_pool.close()
        _meta_pool = None
    for pool in _company_pools.values():
        await pool.close()
    _company_pools.clear()
