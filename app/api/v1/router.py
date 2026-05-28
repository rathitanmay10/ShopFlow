from fastapi import APIRouter

from app.api.v1 import admin, auth, categories, inventory, notifications, orders, payments, products

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(categories.router)
api_v1.include_router(products.router)
api_v1.include_router(inventory.router)
api_v1.include_router(orders.router)
api_v1.include_router(payments.router)
api_v1.include_router(notifications.router)
api_v1.include_router(admin.router)
