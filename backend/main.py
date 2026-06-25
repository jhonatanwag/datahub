from fastapi import FastAPI

app = FastAPI(title="DataHub API", version="1.0.0")

@app.get("/api/health")
async def health():
    return {"ok": True}