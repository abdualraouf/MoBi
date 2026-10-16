from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.product import Product
from app.models.product_item import ProductItem
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.user import User

# In-memory cart store per user session (keyed by user_id)
# Each cart item: {
#   "cart_id": str,
#   "product_id": int,
#   "product_item_id": Optional[int],
#   "name": str,
#   "barcode": str,
#   "imei": Optional[str],
#   "unit_price": float,
#   "buy_price": float,
#   "quantity": int,
#   "has_imei": bool,
#   "max_quantity": int
# }
ACTIVE_CARTS: Dict[int, List[dict]] = {}

def get_user_cart(user_id: int) -> List[dict]:
    if user_id not in ACTIVE_CARTS:
        ACTIVE_CARTS[user_id] = []
    return ACTIVE_CARTS[user_id]

def clear_user_cart(user_id: int):
    ACTIVE_CARTS[user_id] = []

def add_to_cart_by_code(db: Session, user_id: int, code: str) -> tuple[bool, str]:
    """
    Intelligent scanner handler:
    1. Checks if code matches a specific phone IMEI in stock.
    2. Checks if code matches a product barcode (UPC/EAN/custom).
    3. Checks if code matches product ID.
    """
    code = code.strip()
    if not code:
        return False, "الرمز المدخل فارغ"

    cart = get_user_cart(user_id)

    # 1. Search for phone by IMEI
    phone_item = db.query(ProductItem).filter(
        or_(ProductItem.imei == code, ProductItem.imei2 == code),
        ProductItem.status == "in_stock"
    ).first()

    if phone_item:
        # Check if this exact IMEI is already in the cart
        for item in cart:
            if item.get("product_item_id") == phone_item.id:
                return False, f"الجهاز بالرقم التسلسلي {phone_item.imei} مضاف بالفعل إلى السلة"

        product = phone_item.product
        price = phone_item.sell_price if phone_item.sell_price is not None else product.sell_price
        buy_p = phone_item.buy_price if phone_item.buy_price is not None else product.buy_price

        cart.append({
            "cart_id": f"imei_{phone_item.id}",
            "product_id": product.id,
            "product_item_id": phone_item.id,
            "name": f"{product.name} ({phone_item.color or ''} {phone_item.storage or ''})",
            "barcode": product.barcode or "",
            "imei": phone_item.imei,
            "unit_price": float(price),
            "buy_price": float(buy_p),
            "quantity": 1,
            "has_imei": True,
            "max_quantity": 1
        })
        return True, f"تمت إضافة الجهاز IMEI: {phone_item.imei}"

    # 2. Search by Product Barcode
    product = db.query(Product).filter(Product.barcode == code, Product.is_active == True).first()
    
    # 3. Search by ID if numeric
    if not product and code.isdigit():
        product = db.query(Product).filter(Product.id == int(code), Product.is_active == True).first()

    if product:
        if product.has_imei:
            return False, f"هذا المنتج ({product.name}) يتطلب مسح رقم الـ IMEI الخاص بالجهاز المحدد"

        # Check existing item in cart
        for item in cart:
            if item["product_id"] == product.id and not item["has_imei"]:
                if item["quantity"] + 1 > product.quantity:
                    return False, f"الكمية المطلوبة تتجاوز المخزون المتوفر ({product.quantity})"
                item["quantity"] += 1
                return True, f"تمت زيادة كمية {product.name}"

        # New line item
        if product.quantity <= 0:
            return False, f"المنتج {product.name} نفد من المخزون"

        cart.append({
            "cart_id": f"prod_{product.id}",
            "product_id": product.id,
            "product_item_id": None,
            "name": product.name,
            "barcode": product.barcode or "",
            "imei": None,
            "unit_price": float(product.sell_price),
            "buy_price": float(product.buy_price),
            "quantity": 1,
            "has_imei": False,
            "max_quantity": product.quantity
        })
        return True, f"تمت إضافة {product.name}"

    return False, f"لم يتم العثور على صنف أو هاتف مطابق للرمز: {code}"

def update_cart_quantity(user_id: int, cart_id: str, delta: int) -> bool:
    cart = get_user_cart(user_id)
    for i, item in enumerate(cart):
        if item["cart_id"] == cart_id:
            if item["has_imei"]:
                return False  # IMEI devices are strictly quantity 1
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
) -> tuple[Optional[Invoice], str]:
    cart = get_user_cart(user.id)
    if not cart:
        return None, "سلة المبيعات فارغة"

    totals = calculate_cart_totals(user.id, discount)
    paid_amount = float(paid_amount)
    total_amount = totals["total"]
    remaining = max(0.0, total_amount - paid_amount)

    # Generate unique invoice number: INV-YYYYMMDD-XXXX
    date_str = datetime.utcnow().strftime("%Y%m%d")
    today_count = db.query(Invoice).filter(Invoice.created_at >= datetime.utcnow().date()).count() + 1
    invoice_number = f"INV-{date_str}-{today_count:04d}"

    try:
        # Create Invoice record
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
                customer.balance -= remaining  # Negative balance indicates debt

        # Create Invoice Items and update stock
        for item in cart:
            inv_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item["product_id"],
                product_item_id=item["product_item_id"],
                product_name=item["name"],
                imei=item["imei"],
                quantity=item["quantity"],
                buy_price=item["buy_price"],
                unit_price=item["unit_price"],
                total_price=round(item["unit_price"] * item["quantity"], 2)
            )
            db.add(inv_item)

            # Deduct stock
            product = db.query(Product).filter(Product.id == item["product_id"]).first()
            if product:
                if item["has_imei"] and item["product_item_id"]:
                    p_item = db.query(ProductItem).filter(ProductItem.id == item["product_item_id"]).first()
                    if p_item:
                        p_item.status = "sold"
                        p_item.invoice_id = invoice.id
                        p_item.sold_at = datetime.utcnow()
                    product.quantity = max(0, product.quantity - 1)
                else:
                    product.quantity = max(0, product.quantity - item["quantity"])

        db.commit()
        db.refresh(invoice)
        clear_user_cart(user.id)
        return invoice, "تم إصدار الفاتورة بنجاح"
    except Exception as e:
        db.rollback()
        return None, f"فشل حفظ الفاتورة: {str(e)}"
