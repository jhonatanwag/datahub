import json
from config.redis import get_redis

TTL_KPIS    = 300
TTL_CHARTS  = 600
TTL_MONTHLY = 3600


async def cache_get(key: str):
    redis = await get_redis()
    val = await redis.get(key)
    return json.loads(val) if val else None


async def cache_set(key: str, data, ttl: int = TTL_KPIS):
    redis = await get_redis()
    await redis.setex(key, ttl, json.dumps(data, default=str))


async def cache_del_prefix(prefix: str):
    redis = await get_redis()
    keys = await redis.keys(f"{prefix}*")
    if keys:
        await redis.delete(*keys)
