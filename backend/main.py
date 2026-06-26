import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from config.databases import get_meta_pool, close_all_pools
from config.redis import get_redis
from routes import auth, charts, tables, ai, reports, queries, empresas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datahub")

app = FastAPI(title="DataHub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(charts.router)
app.include_router(tables.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(queries.router)
app.include_router(empresas.router)


@app.on_event("startup")
async def startup():
    try:
        await get_meta_pool()
        logger.info("✓ Conectado ao datahub_meta")
    except Exception as e:
        logger.error(f"✗ Falha ao conectar datahub_meta: {e}")

    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("✓ Conectado ao Redis")
    except Exception as e:
        logger.error(f"✗ Falha ao conectar Redis: {e}")

    logger.info(f"DataHub API v1.0.0 rodando na porta {settings.PORT}")


@app.on_event("shutdown")
async def shutdown():
    await close_all_pools()
    logger.info("Pools fechados")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": "1.0.0"}
