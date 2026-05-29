from fastapi import APIRouter

from api.routers import agent, cache, health, runtime, sql

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(agent.router)
api_router.include_router(sql.router)
api_router.include_router(runtime.router)
api_router.include_router(cache.router)
