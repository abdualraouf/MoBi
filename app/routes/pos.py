from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.config import TEMPLATES_DIR
from app.database import get_db
from app.models.product import Product
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user
from app.services import pos_service

router = APIRouter(prefix="/pos", tags=["pos"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("", response_class=HTMLResponse)
def pos_main_page(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    cart = pos_service.get_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    customers = db.query(Customer).order_by(Customer.name.asc()).all()
    settings = db.query(ShopSettings).first()

    # Load top active products for fast tiles
    quick_products = db.query(Product).filter(Product.is_active == True).limit(18).all()

    return templates.TemplateResponse(request=request, name="pos/index.html", context={
        "current_user": current_user,
        "shop_settings": settings,
        "active_page": "pos",
        "cart": cart,
        "totals": totals,
        "customers": customers,
        "quick_products": quick_products,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/add-item", response_class=HTMLResponse)
def pos_add_item(
    request: Request,
    query: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    success, message = pos_service.add_to_cart_by_code(db, current_user.id, query)
    cart = pos_service.get_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    settings = db.query(ShopSettings).first()

    # If failure, we still render the cart with the error header or status
    status_code = 200 if success else 400
    headers = {"HX-Trigger": "scanSuccess" if success else "scanError"}

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": cart,
        "totals": totals,
        "currency": settings.currency if settings else "ر.س",
        "error_msg": message if not success else None
    }, status_code=status_code, headers=headers)

@router.post("/update-qty", response_class=HTMLResponse)
def pos_update_qty(
    request: Request,
    cart_id: str = Form(...),
    delta: int = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    pos_service.update_cart_quantity(current_user.id, cart_id, delta)
    cart = pos_service.get_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": cart,
        "totals": totals,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/remove-item", response_class=HTMLResponse)
def pos_remove_item(
    request: Request,
    cart_id: str = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    pos_service.remove_from_cart(current_user.id, cart_id)
    cart = pos_service.get_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": cart,
        "totals": totals,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/clear-cart", response_class=HTMLResponse)
def pos_clear_cart(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    pos_service.clear_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": [],
        "totals": totals,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/checkout")
def pos_checkout(
    customer_id: Optional[int] = Form(None),
    payment_method: str = Form("cash"),
    paid_amount: float = Form(0.0),
    discount: float = Form(0.0),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    invoice, msg = pos_service.process_checkout(
        db=db,
        user=current_user,
        customer_id=customer_id,
        payment_method=payment_method,
        paid_amount=paid_amount,
        discount=discount,
        notes=notes
    )

    if not invoice:
        return JSONResponse({"success": False, "message": msg}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": msg,
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number
    })

@router.get("/receipt/{invoice_id}", response_class=HTMLResponse)
def pos_view_receipt(
    request: Request,
    invoice_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")

    settings = db.query(ShopSettings).first()
    return templates.TemplateResponse(request=request, name="pos/receipt.html", context={
        "invoice": invoice,
        "settings": settings
    })
