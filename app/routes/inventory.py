from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.template_engine import templates
from app.database import get_db
from app.models.product import Product
from app.models.product_item import ProductItem
from app.models.category import Category
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user

router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("", response_class=HTMLResponse)
def inventory_list(
    request: Request,
    search: Optional[str] = None,
    type: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    query = db.query(Product).join(Category)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_term),
                Product.barcode.ilike(search_term),
                Product.brand.ilike(search_term),
                Product.model.ilike(search_term)
            )
        )

    if type:
        query = query.filter(Category.type == type)

    products = query.order_by(Product.id.desc()).all()
    categories = db.query(Category).all()
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="inventory/index.html", context={
        "current_user": current_user,
        "active_page": "inventory",
        "products": products,
        "categories": categories,
        "search_query": search,
        "type_filter": type,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/product/add")
def add_product(
    category_id: int = Form(...),
    name: str = Form(...),
    barcode: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    buy_price: float = Form(0.0),
    sell_price: float = Form(0.0),
    quantity: int = Form(0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="القسم غير صالح")

    has_imei = (category.type == "phone")
    barcode_val = barcode.strip() if barcode and barcode.strip() else None

    # Check for duplicate barcode if provided
    if barcode_val:
        exists = db.query(Product).filter(Product.barcode == barcode_val).first()
        if exists:
            # Barcode already exists, raise error or handle
            return RedirectResponse(url="/inventory?search=" + barcode_val, status_code=303)

    product = Product(
        category_id=category_id,
        name=name.strip(),
        barcode=barcode_val,
        brand=brand.strip() if brand else None,
        model=model.strip() if model else None,
        buy_price=buy_price,
        sell_price=sell_price,
        min_sell_price=sell_price * 0.9,
        quantity=quantity if not has_imei else 0,
        has_imei=has_imei
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    if has_imei:
        return RedirectResponse(url=f"/inventory/product/{product.id}/imeis", status_code=303)

    return RedirectResponse(url="/inventory", status_code=303)

@router.post("/product/update-stock")
def update_product_stock(
    product_id: int = Form(...),
    new_quantity: int = Form(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product and not product.has_imei:
        product.quantity = max(0, new_quantity)
        db.commit()
    return RedirectResponse(url="/inventory", status_code=303)

@router.get("/product/{product_id}/imeis", response_class=HTMLResponse)
def product_imei_view(
    request: Request,
    product_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    items = db.query(ProductItem).filter(ProductItem.product_id == product_id).order_by(ProductItem.id.desc()).all()
    in_stock_count = sum(1 for i in items if i.status == "in_stock")
    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="inventory/imei_list.html", context={
        "current_user": current_user,
        "active_page": "inventory",
        "product": product,
        "items": items,
        "in_stock_count": in_stock_count,
        "currency": settings.currency if settings else "ر.س"
    })

@router.post("/product/{product_id}/imei/add")
def add_product_imei(
    product_id: int,
    imei: str = Form(...),
    imei2: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    storage: Optional[str] = Form("128GB"),
    condition: str = Form("new"),
    battery_health: Optional[str] = Form("100%"),
    buy_price: Optional[float] = Form(None),
    sell_price: Optional[float] = Form(None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    imei_clean = imei.strip()
    exists = db.query(ProductItem).filter(ProductItem.imei == imei_clean).first()
    if exists:
        return RedirectResponse(url=f"/inventory/product/{product_id}/imeis?error=duplicate_imei", status_code=303)

    item = ProductItem(
        product_id=product.id,
        imei=imei_clean,
        imei2=imei2.strip() if imei2 and imei2.strip() else None,
        color=color.strip() if color else None,
        storage=storage,
        condition=condition,
        battery_health=battery_health.strip() if battery_health else "100%",
        status="in_stock",
        buy_price=buy_price if buy_price is not None else product.buy_price,
        sell_price=sell_price if sell_price is not None else product.sell_price
    )
    db.add(item)
    # Increment total product quantity count
    product.quantity += 1
    db.commit()

    return RedirectResponse(url=f"/inventory/product/{product.id}/imeis", status_code=303)

@router.get("/barcode-labels", response_class=HTMLResponse)
def print_barcode_labels(
    request: Request,
    product_id: Optional[int] = None,
    count: int = 6,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    products = db.query(Product).filter(Product.barcode != None).all()
    selected_product = None
    if product_id:
        selected_product = db.query(Product).filter(Product.id == product_id).first()
    elif products:
        selected_product = products[0]

    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="inventory/barcode_labels.html", context={
        "current_user": current_user,
        "products": products,
        "selected_product": selected_product,
        "label_count": max(1, min(count, 60)),
        "shop_name": settings.shop_name if settings else "MoBi",
        "currency": settings.currency if settings else "ر.س"
    })
