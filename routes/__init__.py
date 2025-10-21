from fastapi import APIRouter

from .route_planner import router as route_planner_router

api_router = APIRouter()
api_router.include_router(route_planner_router, prefix="/routes", tags=["routes"])

__all__ = ["api_router"]
