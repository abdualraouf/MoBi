from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.config import TEMPLATES_DIR, DATABASE_PATH
from app.database import get_db
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("", response_class=HTMLResponse)
def view_settings(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الشاشة مخصصة لمدير النظام فقط")

    settings = db.query(ShopSettings).first()
    return templates.TemplateResponse(request=request, name="settings/index.html", context={
        "current_user": current_user,
        "active_page": "settings",
        "settings": settings
    })

@router.post("/update")
def update_settings(
    shop_name: str = Form(...),
    currency: str = Form(...),
    phone: str = Form(...),
    secondary_phone: Optional[str] = Form(None),
    address: str = Form(...),
    tax_number: Optional[str] = Form(None),
    thermal_width: str = Form("80mm"),
    invoice_footer: str = Form(...),
    repair_terms: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    settings = db.query(ShopSettings).first()
    if not settings:
        settings = ShopSettings()
        db.add(settings)

    settings.shop_name = shop_name.strip()
    settings.currency = currency.strip()
    settings.phone = phone.strip()
    settings.secondary_phone = secondary_phone.strip() if secondary_phone else None
    settings.address = address.strip()
    settings.tax_number = tax_number.strip() if tax_number else None
    settings.thermal_width = thermal_width
    settings.invoice_footer = invoice_footer.strip()
    settings.repair_terms = repair_terms.strip()

    db.commit()
    return RedirectResponse(url="/settings?success=1", status_code=303)

@router.get("/backup-db")
def download_backup(
    current_user: User = Depends(require_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    if not DATABASE_PATH.exists():
        raise HTTPException(status_code=404, detail="قاعدة البيانات غير موجودة")

    return FileResponse(
        path=str(DATABASE_PATH),
        filename=f"mobi_backup_{DATABASE_PATH.name}",
        media_type="application/octet-stream"
    )
