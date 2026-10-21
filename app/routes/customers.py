from typing import Optional
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.template_engine import templates
from app.database import get_db
from app.models.customer import Customer
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user

router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("", response_class=HTMLResponse)
def list_customers(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    customers = db.query(Customer).order_by(Customer.id.desc()).all()
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="customers/index.html", context={
        "current_user": current_user,
        "active_page": "customers",
        "customers": customers,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/create")
def create_customer(
    name: str = Form(...),
    phone: str = Form(...),
    address: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    phone_clean = phone.strip()
    existing = db.query(Customer).filter(Customer.phone == phone_clean).first()
    if existing:
        return RedirectResponse(url="/customers", status_code=303)

    customer = Customer(
        name=name.strip(),
        phone=phone_clean,
        address=address.strip() if address else None,
        notes=notes.strip() if notes else None
    )
    db.add(customer)
    db.commit()
    return RedirectResponse(url="/customers", status_code=303)

@router.post("/create-quick")
def create_customer_quick(
    name: str = Form(...),
    phone: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    phone_clean = phone.strip()
    existing = db.query(Customer).filter(Customer.phone == phone_clean).first()
    if existing:
        return JSONResponse({
            "success": True,
            "customer": {"id": existing.id, "name": existing.name, "phone": existing.phone}
        })

    customer = Customer(name=name.strip(), phone=phone_clean)
    db.add(customer)
    db.commit()
    db.refresh(customer)

    return JSONResponse({
        "success": True,
        "customer": {"id": customer.id, "name": customer.name, "phone": customer.phone}
    })
