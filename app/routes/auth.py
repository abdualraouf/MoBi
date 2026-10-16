from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.config import TEMPLATES_DIR, SESSION_COOKIE_NAME
from app.database import get_db
from app.models.user import User
from app.models.settings import ShopSettings
from app.services.auth_service import verify_password, create_session_token, verify_session_token

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Retrieve the currently authenticated user from signed session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    payload = verify_session_token(token)
    if not payload or "user_id" not in payload:
        return None
    user = db.query(User).filter(User.id == payload["user_id"], User.is_active == True).first()
    return user

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that ensures user is logged in, or raises redirect."""
    user = get_current_user(request, db)
    if not user:
        raise RedirectException(url="/auth/login")
    return user

class RedirectException(Exception):
    def __init__(self, url: str):
        self.url = url

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/pos", status_code=302)
    settings = db.query(ShopSettings).first()
    return templates.TemplateResponse(request=request, name="auth/login.html", context={
        "shop_settings": settings,
        "current_user": None
    })

@router.post("/login")
def login_action(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    settings = db.query(ShopSettings).first()
    user = db.query(User).filter(User.username == username.strip(), User.is_active == True).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={
            "shop_settings": settings,
            "current_user": None,
            "error_msg": "اسم المستخدم أو كلمة المرور غير صحيحة"
        }, status_code=400)

    token = create_session_token(user)
    redirect_target = "/pos" if user.role in ["cashier", "admin"] else "/repairs"
    res = RedirectResponse(url=redirect_target, status_code=303)
    res.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,  # 7 days
        samesite="lax"
    )
    return res

@router.get("/logout")
def logout_action():
    res = RedirectResponse(url="/auth/login", status_code=303)
    res.delete_cookie(SESSION_COOKIE_NAME)
    return res
