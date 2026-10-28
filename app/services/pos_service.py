import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.product import Product
from app.models.attribute_value import ProductAttributeValue
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.user import User

# In-memory cart store per user session (keyed by user_id)
# Each cart item:
# {
#   "cart_id": str,
#   "product_id": int,
#   "name": str,
#   "barcode": str,
#   "unit_price": float,
#   "buy_price": float,
#   "min_price": float,
#   "quantity": int,
#   "is_unit": bool,
#   "max_quantity": int,
#   "attributes": list[dict]
# }
ACTIVE_CARTS: Dict[int, List[dict]] = {}

def get_user_cart(user_id: int) -> List[dict]:
    if user_id not in ACTIVE_CARTS:
        ACTIVE_CARTS[user_id] = []
    return ACTIVE_CARTS[user_id]

def clear_user_cart(user_id: int):
    ACTIVE_CARTS[user_id] = []

def _add_product_to_cart(cart: List[dict], product: Product) -> Tuple[bool, str]:
    if not product.is_active or product.is_archived:
        return False, f"المنتج ({product.name}) غير متاح أو مؤرشف"

    if product.product_type and not product.product_type.show_in_pos:
        return False, f"الصنف ({product.name}) غير معروض للبيع في نقطة البيع (مخصص للصيانة فقط)"

    if product.quantity <= 0:
        return False, f"المنتج ({product.name}) نفد من المخزون"

    # Unit product handling (e.g. phones with unique IMEI/serial)
    if product.is_unit:
        for item in cart:
            if item["product_id"] == product.id:
                uniq = product.primary_unique_value or product.barcode
                return False, f"الجهاز ({product.name} - {uniq}) مضاف بالفعل إلى السلة"

        cart.append({
            "cart_id": f"unit_{product.id}",
            "product_id": product.id,
            "name": product.name,
            "barcode": product.barcode or "",
            "unit_price": float(product.sell_price),
            "buy_price": float(product.buy_price),
            "min_price": float(product.min_sell_price),
            "quantity": 1,
            "is_unit": True,
            "max_quantity": 1,
            "attributes": [
                {
                    "name": a["name"],
                    "value": a["value"],
                    "is_unique": a.get("is_unique", False),
                    "show_on_receipt": a.get("show_on_receipt", False)
                }
                for a in product.display_attributes
            ]
        })
        uniq_info = f" ({product.primary_unique_value})" if product.primary_unique_value else ""
        return True, f"تمت إضافة الجهاز: {product.name}{uniq_info}"

    # Bulk product handling (accessories, cables, etc.)
    for item in cart:
        if item["product_id"] == product.id and not item["is_unit"]:
            if item["quantity"] + 1 > product.quantity:
                return False, f"الكمية المطلوبة تتجاوز المخزون المتوفر ({product.quantity})"
            item["quantity"] += 1
            return True, f"تمت زيادة كمية {product.name}"

    cart.append({
        "cart_id": f"prod_{product.id}",
        "product_id": product.id,
        "name": product.name,
        "barcode": product.barcode or "",
        "unit_price": float(product.sell_price),
        "buy_price": float(product.buy_price),
        "min_price": float(product.min_sell_price),
        "quantity": 1,
        "is_unit": False,
        "max_quantity": product.quantity,
        "attributes": [
            {
                "name": a["name"],
                "value": a["value"],
                "is_unique": a.get("is_unique", False),
                "show_on_receipt": a.get("show_on_receipt", False)
            }
            for a in product.display_attributes
        ]
    })
    return True, f"تمت إضافة {product.name}"

def add_to_cart_by_code(db: Session, user_id: int, code: str) -> Tuple[bool, str]:
    """
    Intelligent scanner & search handler:
    1. Check exact barcode match.
    2. Check exact unique attribute value match (e.g. IMEI, Serial Number).
    3. Check product ID if numeric.
    """
    code = (code or "").strip()
    if not code:
        return False, "الرمز المدخل فارغ"

    cart = get_user_cart(user_id)

    # 1. Exact Barcode Match
    product = db.query(Product).filter(
        Product.barcode == code,
        Product.is_active == True,
        Product.is_archived == False
    ).first()

    # 2. Match on custom attribute values (IMEI, Serial, etc.)
    if not product:
        attr_val = db.query(ProductAttributeValue).filter(
            ProductAttributeValue.value == code
        ).join(Product).filter(
            Product.is_active == True,
            Product.is_archived == False
        ).first()

        if attr_val and attr_val.product:
            product = attr_val.product

    # 3. Match on Product ID
    if not product and code.isdigit():
        product = db.query(Product).filter(
            Product.id == int(code),
            Product.is_active == True,
            Product.is_archived == False
        ).first()

    if product:
        return _add_product_to_cart(cart, product)

    return False, f"لم يتم العثور على صنف أو جهاز مطابق للرمز: {code}"

def add_to_cart_by_product_id(db: Session, user_id: int, product_id: int) -> Tuple[bool, str]:
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True,
        Product.is_archived == False
    ).first()

    if not product:
        return False, "المنتج غير موجود أو مؤرشف"

    cart = get_user_cart(user_id)
    return _add_product_to_cart(cart, product)

def update_cart_quantity(user_id: int, cart_id: str, delta: int) -> bool:
    cart = get_user_cart(user_id)
    for i, item in enumerate(cart):
        if item["cart_id"] == cart_id:
            if item["is_unit"]:
                return False  # Unit devices are strictly quantity 1
            new_qty = item["quantity"] + delta
            if new_qty <= 0:
                cart.pop(i)
                return True
            if new_qty > item["max_quantity"]:
                return False
            item["quantity"] = new_qty
            return True
    return False

def remove_from_cart(user_id: int, cart_id: str):
    cart = get_user_cart(user_id)
    ACTIVE_CARTS[user_id] = [item for item in cart if item["cart_id"] != cart_id]

def calculate_cart_totals(user_id: int, discount: float = 0.0) -> dict:
    cart = get_user_cart(user_id)
    subtotal = sum(item["unit_price"] * item["quantity"] for item in cart)
    discount = max(0.0, float(discount))
    total = max(0.0, subtotal - discount)
    return {
        "items_count": sum(item["quantity"] for item in cart),
        "lines_count": len(cart),
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "total": round(total, 2)
    }

def process_checkout(
    db: Session,
    user: User,
    customer_id: Optional[int],
    payment_method: str,
    paid_amount: float,
    discount: float = 0.0,
    notes: Optional[str] = None
) -> Tuple[Optional[Invoice], str]:
    cart = get_user_cart(user.id)
    if not cart:
        return None, "سلة المبيعات فارغة"

    totals = calculate_cart_totals(user.id, discount)
    paid_amount = float(paid_amount)
    total_amount = totals["total"]
    remaining = max(0.0, total_amount - paid_amount)

    # Validate stock before processing
    for item in cart:
        prod = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not prod or prod.quantity < item["quantity"]:
            prod_name = prod.name if prod else item["name"]
            return None, f"عذراً، المخزون المتوفر من ({prod_name}) غير كافٍ لإتمام الفاتورة"

    # Generate unique invoice number: INV-YYYYMMDD-XXXX
    date_str = datetime.utcnow().strftime("%Y%m%d")
    today_count = db.query(Invoice).filter(Invoice.created_at >= datetime.utcnow().date()).count() + 1
    invoice_number = f"INV-{date_str}-{today_count:04d}"

    try:
        invoice = Invoice(
            invoice_number=invoice_number,
            customer_id=customer_id,
            user_id=user.id,
            subtotal=totals["subtotal"],
            discount=totals["discount"],
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining,
            payment_method=payment_method,
            notes=notes
        )
        db.add(invoice)
        db.flush()

        # Update customer balance if debt
        if remaining > 0 and customer_id:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if customer:
                customer.balance -= remaining

        # Create Invoice Items and deduct stock
        for item in cart:
            snapshot_json = json.dumps(item.get("attributes", []), ensure_ascii=False)
            inv_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item["product_id"],
                product_name=item["name"],
                attributes_snapshot=snapshot_json,
                quantity=item["quantity"],
                buy_price=item["buy_price"],
                unit_price=item["unit_price"],
                total_price=round(item["unit_price"] * item["quantity"], 2)
            )
            db.add(inv_item)

            # Deduct product stock
            product = db.query(Product).filter(Product.id == item["product_id"]).first()
            if product:
                product.quantity = max(0, product.quantity - item["quantity"])

        db.commit()
        db.refresh(invoice)
        clear_user_cart(user.id)
        return invoice, "تم إصدار الفاتورة بنجاح"
    except Exception as e:
        db.rollback()
        return None, f"فشل حفظ الفاتورة: {str(e)}"
