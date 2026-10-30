from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.template_engine import templates
from app.database import get_db
from app.models.user import User
from app.models.product_type import ProductType, TypeAttribute
from app.models.tag import Tag, TAG_COLORS
from app.models.product import Product
from app.models.settings import ShopSettings
from app.routes.auth import require_user, require_admin
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

def _safe_return_url(url: Optional[str], default: str = "/inventory") -> str:
    """Ensure redirect URL is a safe local relative path or same-host URL."""
    if not url:
        return default
    clean = url.strip()
    if clean.startswith("/") and not clean.startswith("//"):
        return clean
    if clean.startswith("http://127.0.0.1") or clean.startswith("http://localhost"):
        return clean
    return default

# ==============================================================================
# Main Inventory Hub (Tabs: Products, Types, Tags)
# ==============================================================================

@router.get("", response_class=HTMLResponse)
def inventory_main(
    request: Request,
    tab: str = "products",
    q: Optional[str] = None,
    scope: str = "all",
    type_id: Optional[str] = Query(None),
    tags: List[str] = Query(default=[]),
    hide_out: Optional[str] = Query(None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # Guard: only admin can view types and tags tabs
    if tab in ("types", "tags") and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الشاشة مخصصة لمدير النظام فقط")

    # Safely parse integer and boolean parameters from HTML forms/links (empty string becomes None/False)
    clean_type_id = int(type_id) if type_id and str(type_id).strip().isdigit() else None
    clean_tags = [int(t) for t in tags if str(t).strip().isdigit()]
    clean_hide_out = str(hide_out).strip().lower() in ("true", "1", "on", "yes") if hide_out else False

    settings = db.query(ShopSettings).first()
    all_types = db.query(ProductType).order_by(ProductType.sort_order.asc(), ProductType.id.asc()).all()
    all_tags = db.query(Tag).order_by(Tag.sort_order.asc(), Tag.id.asc()).all()

    products = []
    if tab == "products":
        products = inventory_service.query_products(
            db,
            q=q,
            scope=scope,
            type_id=clean_type_id,
            tag_ids=tuple(clean_tags),
            hide_out=clean_hide_out
        )

    return templates.TemplateResponse(request=request, name="inventory/index.html", context={
        "current_user": current_user,
        "active_page": "inventory",
        "tab": tab,
        "products": products,
        "all_types": all_types,
        "all_tags": all_tags,
        "tag_colors": TAG_COLORS,
        "q": q or "",
        "scope": scope,
        "type_id": clean_type_id,
        "selected_tags": clean_tags,
        "hide_out": clean_hide_out,
        "currency": settings.currency if settings else "د.ل"
    })


# ==============================================================================
# Product Form Modals (HTMX Partials)
# ==============================================================================

@router.get("/product/new", response_class=HTMLResponse)
def product_new_modal(
    request: Request,
    type_id: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    clean_type_id = int(type_id) if type_id and str(type_id).strip().isdigit() else None
    types = db.query(ProductType).filter(ProductType.is_archived == False).order_by(ProductType.sort_order.asc()).all()
    tags = db.query(Tag).order_by(Tag.sort_order.asc()).all()
    selected_type = None
    if clean_type_id:
        selected_type = db.query(ProductType).filter(ProductType.id == clean_type_id).first()
    if not selected_type and types:
        selected_type = types[0]

    return templates.TemplateResponse(request=request, name="inventory/_product_form.html", context={
        "mode": "new",
        "product": None,
        "types": types,
        "tags": tags,
        "selected_type": selected_type,
        "selected_tag_ids": [],
        "attr_values": {},
        "error_msg": None,
        "field_errors": {}
    })


@router.get("/product/{product_id}/edit", response_class=HTMLResponse)
def product_edit_modal(
    request: Request,
    product_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    types = db.query(ProductType).order_by(ProductType.sort_order.asc()).all()
    tags = db.query(Tag).order_by(Tag.sort_order.asc()).all()

    return templates.TemplateResponse(request=request, name="inventory/_product_form.html", context={
        "mode": "edit",
        "product": product,
        "types": types,
        "tags": tags,
        "selected_type": product.product_type,
        "selected_tag_ids": [t.id for t in product.tags],
        "attr_values": product.attr_map(),
        "error_msg": None,
        "field_errors": {}
    })


@router.get("/product/{product_id}/duplicate", response_class=HTMLResponse)
def product_duplicate_modal(
    request: Request,
    product_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    prefill = inventory_service.duplicate_prefill(db, product_id)
    types = db.query(ProductType).filter(ProductType.is_archived == False).order_by(ProductType.sort_order.asc()).all()
    tags = db.query(Tag).order_by(Tag.sort_order.asc()).all()
    selected_type = db.query(ProductType).filter(ProductType.id == prefill["type_id"]).first()

    return templates.TemplateResponse(request=request, name="inventory/_product_form.html", context={
        "mode": "duplicate",
        "product": prefill,
        "types": types,
        "tags": tags,
        "selected_type": selected_type,
        "selected_tag_ids": prefill["tag_ids"],
        "attr_values": prefill["attr_values"],
        "error_msg": None,
        "field_errors": {}
    })


@router.get("/type/{type_id}/fields", response_class=HTMLResponse)
def type_attribute_fields(
    request: Request,
    type_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        raise HTTPException(status_code=404, detail="النوع غير موجود")

    return templates.TemplateResponse(request=request, name="inventory/_attribute_fields.html", context={
        "product_type": pt,
        "attr_values": {},
        "field_errors": {}
    })


@router.get("/type-fields", response_class=HTMLResponse)
def type_attribute_fields_query(
    request: Request,
    type_id: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    clean_type_id = int(type_id) if type_id and str(type_id).strip().isdigit() else None
    pt = db.query(ProductType).filter(ProductType.id == clean_type_id).first() if clean_type_id else None
    return templates.TemplateResponse(request=request, name="inventory/_attribute_fields.html", context={
        "product_type": pt,
        "attr_values": {},
        "field_errors": {}
    })


@router.post("/product/save")
async def product_save(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    form = await request.form()
    product_id_str = form.get("product_id")
    product_id = int(product_id_str) if product_id_str and product_id_str.strip().isdigit() else None
    type_id = int(form.get("type_id", 0))
    name = form.get("name", "").strip()
    barcode = form.get("barcode", "").strip() or None
    buy_price = float(form.get("buy_price") or 0.0)
    sell_price = float(form.get("sell_price") or 0.0)
    min_sell_price = float(form.get("min_sell_price") or (sell_price * 0.9))
    quantity = int(form.get("quantity") or 0)
    alert_quantity = int(form.get("alert_quantity") or 3)
    unit = form.get("unit", "قطعة").strip()
    tag_ids = [int(t) for t in form.getlist("tags") if str(t).isdigit()]
    return_url = _safe_return_url(form.get("return_url", "/inventory"))

    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt and not product_id:
        raise HTTPException(status_code=400, detail="النوع غير صالح")

    target_pt = pt if pt else db.query(Product).filter(Product.id == product_id).first().product_type
    attr_values = inventory_service.parse_attribute_form(dict(form), target_pt)

    try:
        if not name:
            raise inventory_service.InventoryError("اسم الصنف إلزامي", {"name": "اسم الصنف إلزامي"})

        if product_id:
            product = inventory_service.update_product(
                db, product_id, name, barcode, buy_price, sell_price, min_sell_price,
                quantity, alert_quantity, unit, attr_values, tag_ids
            )
        else:
            product = inventory_service.create_product(
                db, type_id, name, barcode, buy_price, sell_price, min_sell_price,
                quantity, alert_quantity, unit, attr_values, tag_ids
            )

        # Success: if HTMX, trigger client-side redirect or reload
        if request.headers.get("HX-Request"):
            response = Response()
            response.headers["HX-Redirect"] = return_url
            return response
        return RedirectResponse(url=return_url, status_code=303)

    except inventory_service.InventoryError as e:
        types = db.query(ProductType).filter(ProductType.is_archived == False).order_by(ProductType.sort_order.asc()).all()
        tags = db.query(Tag).order_by(Tag.sort_order.asc()).all()
        dummy_prod = {
            "id": product_id,
            "type_id": type_id,
            "name": name,
            "barcode": barcode or "",
            "buy_price": buy_price,
            "sell_price": sell_price,
            "min_sell_price": min_sell_price,
            "quantity": quantity,
            "alert_quantity": alert_quantity,
            "unit": unit
        }
        is_htmx = bool(request.headers.get("HX-Request"))
        return templates.TemplateResponse(
            request=request,
            name="inventory/_product_form.html",
            context={
                "mode": "edit" if product_id else "new",
                "product": dummy_prod,
                "types": types,
                "tags": tags,
                "selected_type": target_pt,
                "selected_tag_ids": tag_ids,
                "attr_values": attr_values,
                "error_msg": e.message,
                "field_errors": e.field_errors
            },
            status_code=200 if is_htmx else 422
        )


@router.post("/product/{product_id}/archive")
def product_archive(
    product_id: int,
    return_url: str = Form("/inventory"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.set_product_archived(db, product_id, True)
    return RedirectResponse(url=_safe_return_url(return_url), status_code=303)


@router.post("/product/{product_id}/restore")
def product_restore(
    product_id: int,
    return_url: str = Form("/inventory"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.set_product_archived(db, product_id, False)
    return RedirectResponse(url=_safe_return_url(return_url), status_code=303)


@router.post("/product/{product_id}/move")
def product_move(
    product_id: int,
    direction: str = Query("up"),
    return_url: str = Query("/inventory"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.move(db, Product, product_id, -1 if direction == "up" else 1)
    return RedirectResponse(url=_safe_return_url(return_url), status_code=303)


@router.post("/product/update-stock")
def product_update_stock(
    product_id: int = Form(...),
    new_quantity: int = Form(...),
    return_url: str = Form("/inventory"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.update_stock(db, product_id, new_quantity)
    return RedirectResponse(url=_safe_return_url(return_url), status_code=303)


# ==============================================================================
# Product Types & Attributes Management (Admin only)
# ==============================================================================

@router.post("/types/create")
def type_create(
    name: str = Form(...),
    icon: str = Form("📦"),
    show_in_pos: Optional[str] = Form(None),
    use_in_repairs: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        pt = inventory_service.create_type(
            db,
            name=name,
            icon=icon,
            show_in_pos=(show_in_pos in ("1", "on", "true")),
            use_in_repairs=(use_in_repairs in ("1", "on", "true"))
        )
        return RedirectResponse(url=f"/inventory/types/{pt.id}", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory?tab=types&error={e.message}", status_code=303)


@router.get("/types/{type_id}", response_class=HTMLResponse)
def type_editor(
    request: Request,
    type_id: int,
    error: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        raise HTTPException(status_code=404, detail="النوع غير موجود")

    all_other_types = db.query(ProductType).filter(ProductType.id != type_id, ProductType.is_archived == False).all()
    products_count = db.query(Product).filter(Product.type_id == type_id).count()

    # Pre-curated local emojis for device & electronics shop
    EMOJI_PICKER = [
        "📱", "📲", "🔌", "🔋", "🎧", "🛡️", "🛠️", "⌚",
        "💻", "🖥️", "📷", "🎮", "💾", "🔊", "🧲", "🪛",
        "📦", "🎁", "🧴", "🔦", "⚡", "🖱️", "⌨️", "🧩"
    ]

    return templates.TemplateResponse(request=request, name="inventory/type_editor.html", context={
        "current_user": current_user,
        "active_page": "inventory",
        "product_type": pt,
        "all_other_types": all_other_types,
        "products_count": products_count,
        "emoji_picker": EMOJI_PICKER,
        "error_msg": error
    })


@router.post("/types/{type_id}/update")
def type_update(
    type_id: int,
    name: str = Form(...),
    icon: str = Form("📦"),
    show_in_pos: Optional[str] = Form(None),
    use_in_repairs: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.update_type(
            db,
            type_id=type_id,
            name=name,
            icon=icon,
            show_in_pos=(show_in_pos in ("1", "on", "true")),
            use_in_repairs=(use_in_repairs in ("1", "on", "true"))
        )
        return RedirectResponse(url=f"/inventory/types/{type_id}?success=1", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory/types/{type_id}?error={e.message}", status_code=303)


@router.post("/types/{type_id}/attributes/add")
def type_attribute_add(
    type_id: int,
    name: str = Form(...),
    field_kind: str = Form("text"),
    options_text: Optional[str] = Form(None),
    is_required: Optional[str] = Form(None),
    is_unique: Optional[str] = Form(None),
    show_on_receipt: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.add_attribute(
            db,
            type_id=type_id,
            name=name,
            field_kind=field_kind,
            options_text=options_text,
            is_required=(is_required in ("1", "on", "true")),
            is_unique=(is_unique in ("1", "on", "true")),
            show_on_receipt=(show_on_receipt in ("1", "on", "true"))
        )
        return RedirectResponse(url=f"/inventory/types/{type_id}", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory/types/{type_id}?error={e.message}", status_code=303)


@router.post("/attributes/{attribute_id}/update")
def attribute_update(
    attribute_id: int,
    name: str = Form(...),
    field_kind: str = Form("text"),
    options_text: Optional[str] = Form(None),
    is_required: Optional[str] = Form(None),
    is_unique: Optional[str] = Form(None),
    show_on_receipt: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    attr = db.query(TypeAttribute).filter(TypeAttribute.id == attribute_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="الخاصية غير موجودة")
    type_id = attr.type_id
    try:
        inventory_service.update_attribute(
            db,
            attribute_id=attribute_id,
            name=name,
            field_kind=field_kind,
            options_text=options_text,
            is_required=(is_required in ("1", "on", "true")),
            is_unique=(is_unique in ("1", "on", "true")),
            show_on_receipt=(show_on_receipt in ("1", "on", "true"))
        )
        return RedirectResponse(url=f"/inventory/types/{type_id}", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory/types/{type_id}?error={e.message}", status_code=303)


@router.post("/attributes/{attribute_id}/delete")
def attribute_delete(
    attribute_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    attr = db.query(TypeAttribute).filter(TypeAttribute.id == attribute_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="الخاصية غير موجودة")
    type_id = attr.type_id
    inventory_service.delete_attribute(db, attribute_id)
    return RedirectResponse(url=f"/inventory/types/{type_id}", status_code=303)


@router.post("/attributes/{attribute_id}/move")
def attribute_move(
    attribute_id: int,
    direction: str = Query("up"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    attr = db.query(TypeAttribute).filter(TypeAttribute.id == attribute_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="الخاصية غير موجودة")
    type_id = attr.type_id
    inventory_service.move(db, TypeAttribute, attribute_id, -1 if direction == "up" else 1, type_id=type_id)
    return RedirectResponse(url=f"/inventory/types/{type_id}", status_code=303)


@router.post("/types/{type_id}/archive")
def type_archive(
    type_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.archive_type(db, type_id, True)
    return RedirectResponse(url="/inventory?tab=types", status_code=303)


@router.post("/types/{type_id}/restore")
def type_restore(
    type_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.archive_type(db, type_id, False)
    return RedirectResponse(url="/inventory?tab=types", status_code=303)


@router.post("/types/{type_id}/delete")
def type_delete(
    type_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.delete_type(db, type_id)
        return RedirectResponse(url="/inventory?tab=types", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory?tab=types&error={e.message}", status_code=303)


@router.get("/types/{type_id}/move-preview")
def type_move_preview(
    type_id: int,
    to: int = Query(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        report = inventory_service.preview_move(db, from_type_id=type_id, to_type_id=to)
        return JSONResponse(report)
    except inventory_service.InventoryError as e:
        return JSONResponse({"error": e.message}, status_code=400)


@router.post("/types/{type_id}/move-products")
def type_move_products(
    type_id: int,
    to_type_id: int = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.move_products(db, from_type_id=type_id, to_type_id=to_type_id)
        return RedirectResponse(url="/inventory?tab=types", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory?tab=types&error={e.message}", status_code=303)


@router.post("/types/{type_id}/move")
def type_move(
    type_id: int,
    direction: str = Query("up"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.move(db, ProductType, type_id, -1 if direction == "up" else 1)
    return RedirectResponse(url="/inventory?tab=types", status_code=303)


# ==============================================================================
# Tags Management
# ==============================================================================

@router.post("/tags/create")
def tag_create(
    name: str = Form(...),
    color: str = Form("blue"),
    show_on_shelf: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.create_tag(
            db,
            name=name,
            color=color,
            show_on_shelf=(show_on_shelf in ("1", "on", "true"))
        )
        return RedirectResponse(url="/inventory?tab=tags", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory?tab=tags&error={e.message}", status_code=303)


@router.post("/tags/{tag_id}/update")
def tag_update(
    tag_id: int,
    name: str = Form(...),
    color: str = Form("blue"),
    show_on_shelf: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        inventory_service.update_tag(
            db,
            tag_id=tag_id,
            name=name,
            color=color,
            show_on_shelf=(show_on_shelf in ("1", "on", "true"))
        )
        return RedirectResponse(url="/inventory?tab=tags", status_code=303)
    except inventory_service.InventoryError as e:
        return RedirectResponse(url=f"/inventory?tab=tags&error={e.message}", status_code=303)


@router.post("/tags/{tag_id}/delete")
def tag_delete(
    tag_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.delete_tag(db, tag_id)
    return RedirectResponse(url="/inventory?tab=tags", status_code=303)


@router.post("/tags/{tag_id}/move")
def tag_move(
    tag_id: int,
    direction: str = Query("up"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    inventory_service.move(db, Tag, tag_id, -1 if direction == "up" else 1)
    return RedirectResponse(url="/inventory?tab=tags", status_code=303)


# ==============================================================================
# Barcode Labels Printing
# ==============================================================================

@router.get("/barcode-labels", response_class=HTMLResponse)
def print_barcode_labels(
    request: Request,
    product_id: Optional[str] = Query(None),
    count: Optional[str] = Query("6"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    clean_product_id = int(product_id) if product_id and str(product_id).strip().isdigit() else None
    clean_count = int(count) if count and str(count).strip().isdigit() else 6
    products = db.query(Product).filter(Product.barcode != None, Product.is_active == True).all()
    selected_product = None
    if clean_product_id:
        selected_product = db.query(Product).filter(Product.id == clean_product_id).first()
    elif products:
        selected_product = products[0]

    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="inventory/barcode_labels.html", context={
        "current_user": current_user,
        "products": products,
        "selected_product": selected_product,
        "label_count": max(1, min(clean_count, 60)),
        "shop_name": settings.shop_name if settings else "MoBi",
        "currency": settings.currency if settings else "د.ل"
    })
