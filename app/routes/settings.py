import os
import io
import sqlite3
from datetime import datetime
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
from app.services.auth_service import hash_password
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
    users = db.query(User).order_by(User.id.asc()).all()
    msg_map = {
        "1": "تم حفظ الإعدادات والشعار بنجاح",
        "pwd": "تم تحديث كلمة المرور بنجاح",
        "user_added": "تم إنشاء حساب المستخدم بنجاح",
        "user_toggled": "تم تحديث حالة الحساب بنجاح"
    }
    success_key = request.query_params.get("success")
    return templates.TemplateResponse(request=request, name="settings/index.html", context={
        "current_user": current_user,
        "active_page": "settings",
        "settings": settings,
        "users": users,
        "success_msg": msg_map.get(success_key),
        "error_msg": request.query_params.get("error")
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

    # Create an atomic online SQLite snapshot so active transactions never corrupt the backup
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = UPLOADS_DIR / "mobi_atomic_backup.db"
    try:
        src_conn = sqlite3.connect(str(DATABASE_PATH))
        dst_conn = sqlite3.connect(str(snapshot_path))
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        serve_path = snapshot_path
    except Exception:
        serve_path = DATABASE_PATH

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=str(serve_path),
        filename=f"mobi_backup_{stamp}.db",
        media_type="application/octet-stream"
    )


@router.post("/users/change-password")
def change_user_password(
    user_id: int = Form(...),
    new_password: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    clean_pwd = new_password.strip()
    if len(clean_pwd) < 4:
        return RedirectResponse(url="/settings?error=كلمة المرور يجب أن لا تقل عن 4 خانات", status_code=303)

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/settings?error=المستخدم غير موجود", status_code=303)

    target_user.hashed_password = hash_password(clean_pwd)
    db.commit()
    return RedirectResponse(url="/settings?success=pwd", status_code=303)


@router.post("/users/create")
def create_new_user(
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("cashier"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    clean_user = username.strip()
    clean_name = full_name.strip()
    clean_pwd = password.strip()
    if not clean_user or not clean_name or len(clean_pwd) < 4:
        return RedirectResponse(url="/settings?error=يرجى ملء كافة حقول المستخدم بكلمة مرور لا تقل عن 4 خانات", status_code=303)

    if role not in ("admin", "cashier", "technician"):
        role = "cashier"

    exists = db.query(User).filter(User.username == clean_user).first()
    if exists:
        return RedirectResponse(url=f"/settings?error=اسم المستخدم ({clean_user}) مسجل مسبقاً", status_code=303)

    new_u = User(
        username=clean_user,
        full_name=clean_name,
        hashed_password=hash_password(clean_pwd),
        role=role,
        is_active=True
    )
    db.add(new_u)
    db.commit()
    return RedirectResponse(url="/settings?success=user_added", status_code=303)


@router.post("/users/{user_id}/toggle")
def toggle_user_active(
    user_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الصلاحية للمدير فقط")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/settings?error=المستخدم غير موجود", status_code=303)

    if target_user.id == current_user.id:
        return RedirectResponse(url="/settings?error=لا يمكنك تعطيل حسابك الشخصي النشط حالياً", status_code=303)

    target_user.is_active = not target_user.is_active
    db.commit()
    return RedirectResponse(url="/settings?success=user_toggled", status_code=303)
