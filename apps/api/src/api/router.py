from fastapi import APIRouter

from src.api.v1 import categories, chat, compare, health, products

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(compare.router)
api_router.include_router(chat.router)

