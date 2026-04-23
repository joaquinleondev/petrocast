from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.v1.endpoints.health import router as health_router
from src.api.v1.router import router as v1_router

app = FastAPI(
    title="Oil & Gas Forecast API",
    version="1.0.0",
    description="API para consultar el listado de pozos y sus pronósticos de producción.",
)

app.include_router(v1_router)
app.include_router(health_router, prefix="/health", tags=["health"])

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
