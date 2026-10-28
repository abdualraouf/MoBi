from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.template_engine import templates
from app.database import get_db
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.tag import Tag
from app.models.attribute_value import ProductAttributeValue
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user
from app.services import pos_service, inventory_service

router = APIRouter(prefix="/pos", tags=["pos"])

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

    # POS Shelf: Types enabled for POS & not archived
    shelf_types = db.query(ProductType).filter(
        ProductType.show_in_pos == True,
        ProductType.is_archived == False
    ).order_by(ProductType.sort_order.asc(), ProductType.id.asc()).all()

    # POS Shelf: Tags pinned to POS shelf
    shelf_tags = db.query(Tag).filter(
        Tag.show_on_shelf == True
    ).order_by(Tag.sort_order.asc(), Tag.id.asc()).all()

    # Initial quick products (up to 24 sellable products)
    quick_products = db.query(Product).join(ProductType).filter(
        Product.is_active == True,
        Product.is_archived == False,
        ProductType.show_in_pos == True
    ).order_by(Product.sort_order.asc(), Product.id.asc()).limit(24).all()

    return templates.TemplateResponse(request=request, name="pos/index.html", context={
        "current_user": current_user,
        "shop_settings": settings,
        "active_page": "pos",
        "cart": cart,
        "totals": totals,
        "customers": customers,
        "shelf_types": shelf_types,
        "shelf_tags": shelf_tags,
        "quick_products": quick_products,
        "currency": settings.currency if settings else "د.ل"
    })


@router.get("/picker", response_class=HTMLResponse)
def pos_picker(
    request: Request,
    mode: str = "type",  # "type" or "tag"
    scope_id: Optional[str] = Query(None),
    q: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    clean_scope_id = int(scope_id) if scope_id and str(scope_id).strip().isdigit() else None
    settings = db.query(ShopSettings).first()
    title = "المنتجات"
    icon = "📦"

    query = db.query(Product).filter(
        Product.is_active == True,
        Product.is_archived == False
    )

    if clean_scope_id is not None:
        if mode == "tag":
            tag = db.query(Tag).filter(Tag.id == clean_scope_id).first()
            if tag:
                title = f"مجموعة: {tag.name}"
                icon = "🏷️"
            query = query.join(Product.tags).join(Product.product_type).filter(
                Tag.id == clean_scope_id,
                ProductType.show_in_pos == True
            )
        else:
            # mode == "type"
            pt = db.query(ProductType).filter(ProductType.id == clean_scope_id).first()
            if pt:
                title = pt.name
                icon = pt.icon
            query = query.filter(Product.type_id == clean_scope_id)
    else:
        query = query.filter(False)

    # Search filter within picker
    clean_q = (q or "").strip()
    if clean_q:
        query = query.filter(
            or_(
                Product.name.ilike(f"%{clean_q}%"),
                Product.barcode.ilike(f"%{clean_q}%"),
                Product.attributes.any(ProductAttributeValue.value.ilike(f"%{clean_q}%"))
            )
        )

    products = query.order_by(Product.sort_order.asc(), Product.id.asc()).all()
    groups = inventory_service.build_pos_groups(products)

    return templates.TemplateResponse(request=request, name="pos/_picker_grid.html", context={
        "title": title,
        "icon": icon,
        "mode": mode,
        "scope_id": scope_id,
        "q": clean_q,
        "groups": groups,
        "currency": settings.currency if settings else "د.ل"
    })


@router.get("/picker/group/{product_id}", response_class=HTMLResponse)
def pos_picker_units(
    request: Request,
    product_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    lead = db.query(Product).filter(Product.id == product_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    settings = db.query(ShopSettings).first()

    # Find all units of this model (same type_id and name)
    units = db.query(Product).filter(
        Product.type_id == lead.type_id,
        Product.name == lead.name,
        Product.is_active == True,
        Product.is_archived == False
    ).order_by(Product.quantity.desc(), Product.sort_order.asc(), Product.id.asc()).all()

    return templates.TemplateResponse(request=request, name="pos/_picker_units.html", context={
        "lead": lead,
        "units": units,
        "currency": settings.currency if settings else "د.ل"
    })


@router.post("/add-product", response_class=HTMLResponse)
def pos_add_product(
    request: Request,
    product_id: int = Query(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    success, message = pos_service.add_to_cart_by_product_id(db, current_user.id, product_id)
    cart = pos_service.get_user_cart(current_user.id)
    totals = pos_service.calculate_cart_totals(current_user.id)
    settings = db.query(ShopSettings).first()

    status_code = 200 if success else 400
    headers = {"HX-Trigger": "scanSuccess" if success else "scanError"}

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": cart,
        "totals": totals,
        "currency": settings.currency if settings else "د.ل",
        "error_msg": message if not success else None
    }, status_code=status_code, headers=headers)


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

    status_code = 200 if success else 400
    headers = {"HX-Trigger": "scanSuccess" if success else "scanError"}

    return templates.TemplateResponse(request=request, name="pos/cart_partial.html", context={
        "cart": cart,
        "totals": totals,
        "currency": settings.currency if settings else "د.ل",
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
        "currency": settings.currency if settings else "د.ل"
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
        "currency": settings.currency if settings else "د.ل"
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
        "currency": settings.currency if settings else "د.ل"
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
