from fastapi import FastAPI
from kitchen_admin_api import auth, catalog, food, orders, users
from kitchen_http.application import configure_app


def create_app() -> FastAPI:
    app = configure_app("Hyperlocal Kitchen Platform Admin API")
    for router in (auth.router, users.router, catalog.router, food.router, orders.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
