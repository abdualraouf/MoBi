import os
import io
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from app.config import TEMPLATES_DIR, STATIC_DIR, DATABASE_PATH, UPLOADS_DIR
from app.template_engine import templates
from app.database import get_db
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user
from PIL import Image

router = APIRouter(prefix="/settings", tags=["settings"])

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
        "settings": settings,
        "success_msg": "تم حفظ الإعدادات والشعار بنجاح" if request.query_params.get("success") else None
    })

@router.post("/update")
async def update_settings(
    shop_name: str = Form(...),
    currency: str = Form(...),
    phone: str = Form(...),
    secondary_phone: Optional[str] = Form(None),
    address: str = Form(...),
    tax_number: Optional[str] = Form(None),
    thermal_width: str = Form("80mm"),
    invoice_footer: str = Form(...),
    repair_terms: str = Form(...),
    logo: Optional[UploadFile] = File(None),
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

    # Process custom shop logo upload if provided
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.ico'):
            uploads_dir = UPLOADS_DIR
            uploads_dir.mkdir(parents=True, exist_ok=True)
            
            contents = await logo.read()
            if len(contents) > 0:
                try:
                    img = Image.open(io.BytesIO(contents))
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    
                    # 1. Save standard PNG logo
                    png_path = uploads_dir / "shop_logo.png"
                    img.save(png_path, format="PNG", optimize=True)

                    # 2. Save multi-resolution Windows ICO
                    ico_path = uploads_dir / "shop_icon.ico"
                    img.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

                    settings.logo_path = "/static/uploads/shop_logo.png"
                except Exception as e:
                    print(f"[!] Logo processing error: {e}")

    db.commit()
    return RedirectResponse(url="/settings?success=1", status_code=303)

@router.post("/reset-logo")
def reset_logo(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    settings = db.query(ShopSettings).first()
    if settings:
        settings.logo_path = None
        db.commit()

        uploads_dir = UPLOADS_DIR
        for fname in ("shop_logo.png", "shop_icon.ico"):
            fpath = uploads_dir / fname
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception:
                    pass

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
