import json
import re
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, not_
from app.models.product_type import ProductType, TypeAttribute
from app.models.tag import Tag, product_tags
from app.models.product import Product
from app.models.attribute_value import ProductAttributeValue
from app.models.app_meta import AppMeta

class InventoryError(Exception):
    """Carries a user-facing Arabic message and optional field errors dict."""
    def __init__(self, message: str, field_errors: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.field_errors = field_errors or {}

# ==============================================================================
# Ordering & Sequencing
# ==============================================================================

def next_sort_order(db: Session, model, **filters) -> int:
    query = db.query(func.max(model.sort_order))
    for k, v in filters.items():
        query = query.filter(getattr(model, k) == v)
    max_val = query.scalar()
    return (max_val + 10) if max_val is not None else 10


def move(db: Session, model, obj_id: int, direction: int, **scope_filters):
    """
    Swap sort_order with adjacent item in same model scope.
    direction: -1 for move up (smaller sort_order), +1 for move down (larger sort_order).
    """
    obj = db.query(model).filter(model.id == obj_id).first()
    if not obj:
        return

    query = db.query(model)
    for k, v in scope_filters.items():
        query = query.filter(getattr(model, k) == v)

    if direction < 0:
        # Move up: find the nearest item with smaller sort_order
        neighbour = query.filter(model.sort_order < obj.sort_order).order_by(model.sort_order.desc()).first()
    else:
        # Move down: find the nearest item with larger sort_order
        neighbour = query.filter(model.sort_order > obj.sort_order).order_by(model.sort_order.asc()).first()

    if neighbour:
        obj.sort_order, neighbour.sort_order = neighbour.sort_order, obj.sort_order
        db.commit()


# ==============================================================================
# Barcode Generation & Normalization
# ==============================================================================

def normalize_barcode(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    val = raw.strip()
    return val if val else None


def generate_barcode(db: Session) -> str:
    """Generate the next unique system barcode (MB000123)."""
    meta_seq = db.query(AppMeta).filter(AppMeta.key == "barcode_seq").first()
    if not meta_seq:
        meta_seq = AppMeta(key="barcode_seq", value="0")
        db.add(meta_seq)
        db.flush()

    try:
        seq = int(meta_seq.value)
    except ValueError:
        seq = 0

    while True:
        seq += 1
        meta_seq.value = str(seq)
        code = f"MB{seq:06d}"
        exists = db.query(Product).filter(Product.barcode == code).first()
        if not exists:
            db.commit()
            return code


# ==============================================================================
# Attribute Validation & Parsing
# ==============================================================================

def parse_options_text(text: Optional[str]) -> str:
    """Parse comma/newline separated options into clean JSON list."""
    if not text:
        return json.dumps([], ensure_ascii=False)
    # Split by newline or commas (English & Arabic comma)
    tokens = re.split(r'[\r\n,،]+', text)
    cleaned = []
    seen = set()
    for t in tokens:
        item = t.strip()
        if item and item not in seen:
            seen.add(item)
            cleaned.append(item)
    return json.dumps(cleaned, ensure_ascii=False)


def parse_attribute_form(form_data: dict, product_type: ProductType) -> dict[int, str]:
    """Extract attr_<id> from form data dict and format appropriately."""
    values = {}
    for attr in product_type.attributes:
        key = f"attr_{attr.id}"
        if attr.field_kind == "boolean":
            # Checkbox: "1", "true", "on" means True; absent means False
            raw = form_data.get(key)
            values[attr.id] = "1" if raw in ("1", "true", "on", "yes") else "0"
        else:
            raw = form_data.get(key, "")
            values[attr.id] = str(raw).strip() if raw is not None else ""
    return values


def validate_attribute_values(
    db: Session,
    product_type: ProductType,
    values: dict[int, str],
    product_id: Optional[int] = None
) -> dict[int, str]:
    """Validate attribute values against product_type definitions. Returns {attr_id: error_msg}."""
    errors = {}
    for attr in product_type.attributes:
        val = values.get(attr.id, "").strip()

        # 1. Required check
        if attr.is_required:
            if attr.field_kind == "boolean":
                pass  # Booleans are always "0" or "1"
            elif not val:
                errors[attr.id] = f"خاصية ({attr.name}) إلزامية"
                continue

        if not val:
            continue

        # 2. Number check
        if attr.field_kind == "number":
            try:
                float(val)
            except ValueError:
                errors[attr.id] = f"يجب إدخال قيمة رقمية صحيحة في خاصية ({attr.name})"
                continue

        # 3. Select check
        if attr.field_kind == "select":
            opts = attr.options_list
            if opts and val not in opts:
                errors[attr.id] = f"القيمة المحددة غير صالحة لخاصية ({attr.name})"
                continue

        # 4. Unique check
        if attr.is_unique:
            query = db.query(ProductAttributeValue).filter(
                ProductAttributeValue.attribute_id == attr.id,
                ProductAttributeValue.value == val
            )
            if product_id is not None:
                query = query.filter(ProductAttributeValue.product_id != product_id)
            existing = query.first()
            if existing:
                other_prod = existing.product
                p_name = other_prod.name if other_prod else "منتج آخر"
                p_code = other_prod.barcode if other_prod else ""
                errors[attr.id] = f"القيمة '{val}' مسجلة مسبقاً للمنتج: {p_name} (باركود: {p_code})"

    return errors


# ==============================================================================
# Products Management
# ==============================================================================

def create_product(
    db: Session,
    type_id: int,
    name: str,
    barcode: Optional[str],
    buy_price: float,
    sell_price: float,
    min_sell_price: float,
    quantity: int,
    alert_quantity: int,
    unit: str,
    attr_values: dict[int, str],
    tag_ids: list[int]
) -> Product:
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        raise InventoryError("نوع المنتج المحدد غير صالح", {"type_id": "نوع المنتج غير صالح"})

    field_errors = validate_attribute_values(db, pt, attr_values)
    if field_errors:
        raise InventoryError("يرجى تصحيح أخطاء الخصائص المحددة", field_errors)

    norm_barcode = normalize_barcode(barcode)
    if not norm_barcode:
        norm_barcode = generate_barcode(db)
    else:
        # Check duplicate
        exists = db.query(Product).filter(Product.barcode == norm_barcode).first()
        if exists:
            raise InventoryError(f"الباركود '{norm_barcode}' مسجل مسبقاً للمنتج: {exists.name}", {"barcode": "الباركود مسجل مسبقاً"})

    final_qty = 1 if pt.has_unique_attribute else max(0, quantity)
    order = next_sort_order(db, Product)

    product = Product(
        type_id=pt.id,
        name=name.strip(),
        barcode=norm_barcode,
        buy_price=max(0.0, float(buy_price)),
        sell_price=max(0.0, float(sell_price)),
        min_sell_price=max(0.0, float(min_sell_price)),
        quantity=final_qty,
        alert_quantity=max(0, int(alert_quantity)),
        unit=unit.strip() if unit else "قطعة",
        sort_order=order,
        is_active=True
    )

    # Attach tags
    if tag_ids:
        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
        product.tags = tags

    db.add(product)
    db.flush()

    # Save attribute values
    for attr_id, val in attr_values.items():
        clean_val = val.strip()
        if clean_val:
            db.add(ProductAttributeValue(product_id=product.id, attribute_id=attr_id, value=clean_val))

    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session,
    product_id: int,
    name: str,
    barcode: Optional[str],
    buy_price: float,
    sell_price: float,
    min_sell_price: float,
    quantity: int,
    alert_quantity: int,
    unit: str,
    attr_values: dict[int, str],
    tag_ids: list[int]
) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise InventoryError("المنتج غير موجود")

    pt = product.product_type
    field_errors = validate_attribute_values(db, pt, attr_values, product_id=product.id)
    if field_errors:
        raise InventoryError("يرجى تصحيح أخطاء الخصائص المحددة", field_errors)

    norm_barcode = normalize_barcode(barcode)
    if not norm_barcode:
        raise InventoryError("الباركود إلزامي ولا يمكن حذفه", {"barcode": "الباركود إلزامي"})

    exists = db.query(Product).filter(Product.barcode == norm_barcode, Product.id != product.id).first()
    if exists:
        raise InventoryError(f"الباركود '{norm_barcode}' مسجل مسبقاً لمنتج آخر: {exists.name}", {"barcode": "الباركود مسجل مسبقاً"})

    final_qty = max(0, min(1, quantity)) if pt.has_unique_attribute else max(0, quantity)

    product.name = name.strip()
    product.barcode = norm_barcode
    product.buy_price = max(0.0, float(buy_price))
    product.sell_price = max(0.0, float(sell_price))
    product.min_sell_price = max(0.0, float(min_sell_price))
    product.quantity = final_qty
    product.alert_quantity = max(0, int(alert_quantity))
    product.unit = unit.strip() if unit else "قطعة"

    # Update tags
    tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
    product.tags = tags

    # Update attribute values
    existing_vals = {v.attribute_id: v for v in product.attribute_values}
    for attr in pt.attributes:
        new_val = attr_values.get(attr.id, "").strip()
        if attr.id in existing_vals:
            if new_val:
                existing_vals[attr.id].value = new_val
            else:
                db.delete(existing_vals[attr.id])
        else:
            if new_val:
                db.add(ProductAttributeValue(product_id=product.id, attribute_id=attr.id, value=new_val))

    db.commit()
    db.refresh(product)
    return product


def duplicate_prefill(db: Session, product_id: int) -> dict:
    """Return prefill dictionary for duplicating a product."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise InventoryError("المنتج غير موجود")

    pt = product.product_type
    values = product.attr_map()
    non_unique_attrs = {}
    for attr in pt.attributes:
        if not attr.is_unique:
            non_unique_attrs[attr.id] = values.get(attr.id, "")

    return {
        "type_id": product.type_id,
        "name": product.name,
        "barcode": "",  # Automatically generated on save
        "buy_price": product.buy_price,
        "sell_price": product.sell_price,
        "min_sell_price": product.min_sell_price,
        "quantity": 1,
        "alert_quantity": product.alert_quantity,
        "unit": product.unit,
        "tag_ids": [t.id for t in product.tags],
        "attr_values": non_unique_attrs
    }


def set_product_archived(db: Session, product_id: int, archived: bool):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.is_active = not archived
        db.commit()


def update_stock(db: Session, product_id: int, new_qty: int):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return
    if product.is_unit:
        product.quantity = max(0, min(1, int(new_qty)))
    else:
        product.quantity = max(0, int(new_qty))
    db.commit()


# ==============================================================================
# Product Types & Custom Attributes Management
# ==============================================================================

def create_type(db: Session, name: str, icon: str, show_in_pos: bool, use_in_repairs: bool) -> ProductType:
    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم النوع إلزامي")

    exists = db.query(ProductType).filter(ProductType.name == clean_name).first()
    if exists:
        raise InventoryError(f"النوع '{clean_name}' موجود بالفعل")

    order = next_sort_order(db, ProductType)
    pt = ProductType(
        name=clean_name,
        icon=icon.strip() or "📦",
        show_in_pos=bool(show_in_pos),
        use_in_repairs=bool(use_in_repairs),
        sort_order=order,
        is_archived=False
    )
    db.add(pt)
    db.commit()
    db.refresh(pt)
    return pt


def update_type(db: Session, type_id: int, name: str, icon: str, show_in_pos: bool, use_in_repairs: bool) -> ProductType:
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        raise InventoryError("النوع غير موجود")

    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم النوع إلزامي")

    exists = db.query(ProductType).filter(ProductType.name == clean_name, ProductType.id != type_id).first()
    if exists:
        raise InventoryError(f"الاسم '{clean_name}' مستخدم لنوع آخر")

    pt.name = clean_name
    pt.icon = icon.strip() or "📦"
    pt.show_in_pos = bool(show_in_pos)
    pt.use_in_repairs = bool(use_in_repairs)
    db.commit()
    db.refresh(pt)
    return pt


def add_attribute(
    db: Session,
    type_id: int,
    name: str,
    field_kind: str,
    options_text: Optional[str],
    is_required: bool,
    is_unique: bool,
    show_on_receipt: bool
) -> TypeAttribute:
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        raise InventoryError("النوع غير موجود")

    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم الخاصية إلزامي")

    if is_unique:
        # Check if type has products with quantity > 1
        multi_qty_prod = db.query(Product).filter(Product.type_id == type_id, Product.quantity > 1).first()
        if multi_qty_prod:
            raise InventoryError("لا يمكن جعل الخاصية فريدة لأن بعض المنتجات التابعة لهذا النوع كميتها أكبر من 1.")

    order = next_sort_order(db, TypeAttribute, type_id=type_id)
    opts_json = parse_options_text(options_text) if field_kind == "select" else None

    attr = TypeAttribute(
        type_id=type_id,
        name=clean_name,
        field_kind=field_kind,
        options=opts_json,
        is_required=bool(is_required),
        is_unique=bool(is_unique),
        show_on_receipt=bool(show_on_receipt),
        sort_order=order
    )
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


def update_attribute(
    db: Session,
    attribute_id: int,
    name: str,
    field_kind: str,
    options_text: Optional[str],
    is_required: bool,
    is_unique: bool,
    show_on_receipt: bool
) -> TypeAttribute:
    attr = db.query(TypeAttribute).filter(TypeAttribute.id == attribute_id).first()
    if not attr:
        raise InventoryError("الخاصية غير موجودة")

    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم الخاصية إلزامي")

    # If field_kind changed and values exist -> reject
    if field_kind != attr.field_kind:
        val_count = db.query(ProductAttributeValue).filter(ProductAttributeValue.attribute_id == attribute_id).count()
        if val_count > 0:
            raise InventoryError("لا يمكن تغيير نوع الخانة بعد إدخال قيم لها في المنتجات")

    # If toggling is_unique ON -> verify no duplicate values
    if is_unique and not attr.is_unique:
        # Check product quantities
        multi_qty_prod = db.query(Product).filter(Product.type_id == attr.type_id, Product.quantity > 1).first()
        if multi_qty_prod:
            raise InventoryError("لا يمكن جعل الخاصية فريدة لأن بعض المنتجات كميتها أكبر من 1")

        dups = db.query(ProductAttributeValue.value, func.count(ProductAttributeValue.id))\
            .filter(ProductAttributeValue.attribute_id == attribute_id)\
            .group_by(ProductAttributeValue.value)\
            .having(func.count(ProductAttributeValue.id) > 1)\
            .first()
        if dups:
            raise InventoryError(f"لا يمكن جعل الخاصية فريدة لوجود قيم مكررة بالفعل: '{dups[0]}'")

    attr.name = clean_name
    attr.field_kind = field_kind
    attr.options = parse_options_text(options_text) if field_kind == "select" else None
    attr.is_required = bool(is_required)
    attr.is_unique = bool(is_unique)
    attr.show_on_receipt = bool(show_on_receipt)

    db.commit()
    db.refresh(attr)
    return attr


def delete_attribute(db: Session, attribute_id: int) -> int:
    attr = db.query(TypeAttribute).filter(TypeAttribute.id == attribute_id).first()
    if not attr:
        return 0
    val_count = db.query(ProductAttributeValue).filter(ProductAttributeValue.attribute_id == attribute_id).count()
    db.delete(attr)
    db.commit()
    return val_count


def archive_type(db: Session, type_id: int, archived: bool):
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if pt:
        pt.is_archived = archived
        db.commit()


def delete_type(db: Session, type_id: int):
    pt = db.query(ProductType).filter(ProductType.id == type_id).first()
    if not pt:
        return
    prod_count = db.query(Product).filter(Product.type_id == type_id).count()
    if prod_count > 0:
        raise InventoryError(
            f"لا يمكن حذف هذا النوع لأنه يحتوي على {prod_count} منتج. "
            f"يمكنك نقل المنتجات لنوع آخر أولاً ثم الحذف، أو أرشفة النوع."
        )
    db.delete(pt)
    db.commit()


def preview_move(db: Session, from_type_id: int, to_type_id: int) -> dict:
    from_pt = db.query(ProductType).filter(ProductType.id == from_type_id).first()
    to_pt = db.query(ProductType).filter(ProductType.id == to_type_id).first()
    if not from_pt or not to_pt:
        raise InventoryError("النوع المحدد غير موجود")

    products = db.query(Product).filter(Product.type_id == from_type_id).all()
    from_attrs = {a.id: a for a in from_pt.attributes}
    to_attrs_by_key = {(a.name.strip().casefold(), a.field_kind): a for a in to_pt.attributes}

    dropped_attrs = []
    for a in from_pt.attributes:
        key = (a.name.strip().casefold(), a.field_kind)
        if key not in to_attrs_by_key:
            dropped_attrs.append(a.name)

    return {
        "moved_count": len(products),
        "from_type_name": from_pt.name,
        "to_type_name": to_pt.name,
        "dropped_attributes": dropped_attrs
    }


def move_products(db: Session, from_type_id: int, to_type_id: int) -> dict:
    preview = preview_move(db, from_type_id, to_type_id)
    from_pt = db.query(ProductType).filter(ProductType.id == from_type_id).first()
    to_pt = db.query(ProductType).filter(ProductType.id == to_type_id).first()
    products = db.query(Product).filter(Product.type_id == from_type_id).all()

    to_attrs_by_key = {(a.name.strip().casefold(), a.field_kind): a for a in to_pt.attributes}

    for prod in products:
        old_values = prod.attr_map()
        # Drop existing values
        for v in list(prod.attribute_values):
            db.delete(v)
        db.flush()

        # Remap to new matching attributes
        for from_a in from_pt.attributes:
            val = old_values.get(from_a.id)
            if val:
                key = (from_a.name.strip().casefold(), from_a.field_kind)
                if key in to_attrs_by_key:
                    target_attr = to_attrs_by_key[key]
                    db.add(ProductAttributeValue(
                        product_id=prod.id,
                        attribute_id=target_attr.id,
                        value=val
                    ))

        prod.type_id = to_type_id

    db.commit()
    return preview


# ==============================================================================
# Tags Management
# ==============================================================================

def create_tag(db: Session, name: str, color: str, show_on_shelf: bool) -> Tag:
    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم المجموعة / التاغ إلزامي")

    exists = db.query(Tag).filter(Tag.name == clean_name).first()
    if exists:
        raise InventoryError(f"التاغ '{clean_name}' موجود بالفعل")

    order = next_sort_order(db, Tag)
    tag = Tag(
        name=clean_name,
        color=color if color else "blue",
        show_on_shelf=bool(show_on_shelf),
        sort_order=order
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def update_tag(db: Session, tag_id: int, name: str, color: str, show_on_shelf: bool) -> Tag:
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise InventoryError("التاغ غير موجود")

    clean_name = name.strip()
    if not clean_name:
        raise InventoryError("اسم المجموعة / التاغ إلزامي")

    exists = db.query(Tag).filter(Tag.name == clean_name, Tag.id != tag_id).first()
    if exists:
        raise InventoryError(f"الاسم '{clean_name}' مستخدم لتاغ آخر")

    tag.name = clean_name
    tag.color = color if color else tag.color
    tag.show_on_shelf = bool(show_on_shelf)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int) -> int:
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        return 0
    count = len(tag.products)
    db.delete(tag)
    db.commit()
    return count


# ==============================================================================
# Queries & POS Group Building
# ==============================================================================

def query_products(
    db: Session,
    *,
    q: Optional[str] = None,
    scope: str = "all",  # "all", "sale", "repair", "archived"
    type_id: Optional[int] = None,
    tag_ids: tuple = (),
    hide_out: bool = False
) -> List[Product]:
    query = db.query(Product).join(ProductType)

    # Scope filter
    if scope in ("sale", "sellable"):
        query = query.filter(Product.is_active == True, ProductType.is_archived == False, ProductType.show_in_pos == True)
    elif scope in ("repair", "repairs"):
        query = query.filter(Product.is_active == True, ProductType.is_archived == False, ProductType.use_in_repairs == True)
    elif scope == "archived":
        query = query.filter(or_(Product.is_active == False, ProductType.is_archived == True))
    else:  # "all"
        query = query.filter(Product.is_active == True, ProductType.is_archived == False)

    # Type filter
    if type_id:
        query = query.filter(Product.type_id == type_id)

    # Out of stock filter
    if hide_out:
        query = query.filter(Product.quantity > 0)

    # Tags filter: AND logic (product must match every tag specified)
    if tag_ids:
        for tid in tag_ids:
            query = query.filter(Product.tags.any(Tag.id == tid))

    # Free text search: name, barcode, or attribute value
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(term),
                Product.barcode.ilike(term),
                Product.attribute_values.any(ProductAttributeValue.value.ilike(term))
            )
        )

    return query.order_by(Product.sort_order.asc(), Product.id.asc()).all()


def build_pos_groups(products: List[Product]) -> List[dict]:
    """
    Groups products by (type_id, name.strip().casefold()) for POS picker display.
    Maintains stable positions according to Product.sort_order.
    """
    groups_dict = {}
    for p in products:
        key = (p.type_id, p.name.strip().casefold())
        if key not in groups_dict:
            groups_dict[key] = {
                "key_product_id": p.id,
                "type_id": p.type_id,
                "name": p.name,
                "icon": p.product_type.icon if p.product_type else "📦",
                "is_unit_group": p.is_unit,
                "count_total": 0,
                "units_available": 0,
                "qty_available": 0,
                "prices": set(),
                "sort_order": p.sort_order,
                "products": []
            }
        g = groups_dict[key]
        g["count_total"] += 1
        if p.quantity > 0:
            g["units_available"] += 1
            g["qty_available"] += p.quantity
        g["prices"].add(p.sell_price)
        g["sort_order"] = min(g["sort_order"], p.sort_order)
        g["products"].append(p)

    out = []
    for g in groups_dict.values():
        prices = sorted(g["prices"])
        price_min = prices[0] if prices else 0.0
        price_max = prices[-1] if prices else 0.0
        out.append({
            "key_product_id": g["key_product_id"],
            "type_id": g["type_id"],
            "name": g["name"],
            "icon": g["icon"],
            "is_unit_group": g["is_unit_group"],
            "count_total": g["count_total"],
            "units_available": g["units_available"],
            "qty_available": g["qty_available"],
            "price_min": price_min,
            "price_max": price_max,
            "sort_order": g["sort_order"],
            "is_out_of_stock": (g["qty_available"] <= 0)
        })

    # Sort groups stably by sort_order
    out.sort(key=lambda x: (x["sort_order"], x["key_product_id"]))
    return out
