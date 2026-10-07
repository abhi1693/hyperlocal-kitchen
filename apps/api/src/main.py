from fastapi import FastAPI
from kitchen_api import auth, catalog, follows, notifications, orders, profile
from kitchen_http.application import configure_app


def create_app() -> FastAPI:
    app = configure_app("Hyperlocal Kitchen API")
    for router in (
        auth.router,
        catalog.router,
        follows.router,
        orders.router,
        notifications.router,
        profile.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
