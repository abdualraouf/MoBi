from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import APP_TITLE, VERSION, STATIC_DIR
from app.database_init import init_db
from app.routes.auth import router as auth_router, RedirectException, get_current_user
from app.routes.pos import router as pos_router
from app.routes.inventory import router as inventory_router
from app.routes.repairs import router as repairs_router
from app.routes.customers import router as customers_router
from app.routes.reports import router as reports_router
from app.routes.settings import router as settings_router
from app.database import SessionLocal

app = FastAPI(title=APP_TITLE, version=VERSION)

# Automatically mount static assets locally (Offline-First 100%)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include Application Routers
app.include_router(auth_router)
app.include_router(pos_router)
app.include_router(inventory_router)
app.include_router(repairs_router)
app.include_router(customers_router)
app.include_router(reports_router)
app.include_router(settings_router)

@app.on_event("startup")
def on_startup():
    """Ensure database schema is created and seeded upon application launch."""
    init_db()

@app.exception_handler(RedirectException)
def redirect_exception_handler(request: Request, exc: RedirectException):
    """Handle unauthenticated access and redirect to login page."""
    return RedirectResponse(url=exc.url, status_code=303)

@app.get("/")
def root_index(request: Request):
    """Redirect root path to POS or login based on active session."""
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user:
            return RedirectResponse(url="/pos", status_code=303)
        return RedirectResponse(url="/auth/login", status_code=303)
    finally:
        db.close()
