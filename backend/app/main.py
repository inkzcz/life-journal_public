"""Application composition only: importing this module never creates database tables."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession
from .db import engine
from .calendar import models as calendar_models
from .exchange import models as exchange_models
from . import site_text
from .dependencies import db_dep
from .middleware import csrf_guard
from .settings import Settings
from .routers import tags, discovery, maintenance, recovery, auth, admin, setup, content, archive, blog, templates
from . import album_models, experience_models, v5_models, tag_models, recovery_models, life_models, template_models, blog_models, archive_models, content_models  # Register metadata without any database writes.


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.database_ready = False
        from .api_startup import prepare
        import asyncio
        await asyncio.to_thread(prepare, engine)
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        app.state.database_ready = True
        print("[API] Startup completed", flush=True)
        try:
            yield
        finally:
            app.state.database_ready = False

    from .version import __version__
    app = FastAPI(title='Life Journal', version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request,exc):
        # Pydantic defaults echo rejected input, including passwords. Do not return
        # raw inputs or exception contexts that proxies/tools might retain.
        return JSONResponse({'detail':[{k:e[k] for k in ('loc','msg','type') if k in e} for e in exc.errors()]},status_code=422)

    app.state.database_ready = False
    app.state.settings = settings
    app.middleware('http')(csrf_guard)
    for router in (site_text.router, setup.router, tags.router, discovery.router, maintenance.router, recovery.router, auth.router, admin.router, content.router, archive.router, blog.router, blog.admin, templates.router):
        app.include_router(router)

    @app.get('/api/health')
    def health(db:DBSession=Depends(db_dep)):
        if not app.state.database_ready:
            raise HTTPException(503, '数据库启动门禁尚未通过')
        db.execute(text('SELECT 1'))
        return {'ok':True}

    from .routers import exchange
    app.include_router(exchange.router)
    from .routers import folders,media_recovery,organization,food
    app.include_router(food.router)
    app.include_router(food.admin)
    app.include_router(organization.router)
    app.include_router(folders.router)
    app.include_router(media_recovery.router)
    from .routers import places,itinerary,experiences,photo_albums
    app.include_router(places.router)
    app.include_router(itinerary.router)
    app.include_router(experiences.router)
    app.include_router(photo_albums.router)
    app.include_router(photo_albums.admin)
    from .calendar import router as calendar_router
    app.include_router(calendar_router.router)
    app.include_router(calendar_router.admin)
    return app


app = create_app()
