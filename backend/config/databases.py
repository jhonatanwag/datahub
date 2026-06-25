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


async def query_meta(sql: str, *args):
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def close_all_pools():
    global _meta_pool, _company_pools
    if _meta_pool:
        await _meta_pool.close()
        _meta_pool = None
    for pool in _company_pools.values():
        await pool.close()
    _company_pools.clear()
