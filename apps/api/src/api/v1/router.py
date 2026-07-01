from fastapi import APIRouter

from src.api.v1.endpoints import forecast, prediction, wells

router = APIRouter(prefix="/api/v1")
router.include_router(wells.router, tags=["wells"])
router.include_router(forecast.router, tags=["forecast"])
router.include_router(prediction.router, tags=["predictions"])
