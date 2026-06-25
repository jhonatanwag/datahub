from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from routes.auth import router as auth_router
from routes.queries import router as queries_router
from routes.charts import router as charts_router
from routes.tables import router as tables_router
from routes.ai import router as ai_router
from routes.reports import router as reports_router

app = FastAPI(title="DataHub API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_URL.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)
app.include_router(queries_router)
app.include_router(charts_router)
app.include_router(tables_router)
app.include_router(ai_router)
app.include_router(reports_router)

@app.get("/api/health")
async def health():
    return {"ok": True}