from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.template_engine import templates
from app.database import get_db
from app.models.repair import RepairTicket, RepairPart
from app.models.customer import Customer
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user, require_repairs_tech

router = APIRouter(prefix="/repairs", tags=["repairs"])

def _next_ticket_code(db: Session) -> str:
    """Generate a collision-free sequential repair ticket code for today (local time)."""
    date_str = datetime.now().strftime("%y%m%d")
    prefix = f"REP-{date_str}-"
    existing_codes = [
        r[0] for r in db.query(RepairTicket.ticket_code)
        .filter(RepairTicket.ticket_code.like(f"{prefix}%"))
        .all()
    ]
    max_seq = 0
    for code in existing_codes:
        try:
            seq_part = int(code.split("-")[-1])
            if seq_part > max_seq:
                max_seq = seq_part
        except ValueError:
            pass
    next_seq = max_seq + 1
    while True:
        candidate = f"{prefix}{next_seq:04d}"
        if not db.query(RepairTicket.id).filter(RepairTicket.ticket_code == candidate).first():
            return candidate
        next_seq += 1

@router.get("", response_class=HTMLResponse)
def list_repairs(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    query = db.query(RepairTicket).join(Customer)

    if status:
        query = query.filter(RepairTicket.status == status)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                RepairTicket.ticket_code.ilike(search_term),
                RepairTicket.device_model.ilike(search_term),
                RepairTicket.imei.ilike(search_term),
                Customer.name.ilike(search_term),
                Customer.phone.ilike(search_term)
            )
        )

    tickets = query.order_by(RepairTicket.id.desc()).all()

    # Pre-count statuses for quick tabs
    counts = {
        "all": db.query(RepairTicket).count(),
        "received": db.query(RepairTicket).filter(RepairTicket.status == "received").count(),
        "repairing": db.query(RepairTicket).filter(RepairTicket.status == "repairing").count(),
        "ready": db.query(RepairTicket).filter(RepairTicket.status == "ready").count(),
        "delivered": db.query(RepairTicket).filter(RepairTicket.status == "delivered").count()
    }

    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="repairs/index.html", context={
        "current_user": current_user,
        "active_page": "repairs",
        "tickets": tickets,
        "counts": counts,
        "status_filter": status,
        "search_query": search,
        "currency": settings.currency if settings else "د.ل"
    })

@router.post("/create")
def create_repair_ticket(
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    device_brand: str = Form(...),
    device_model: str = Form(...),
    color: Optional[str] = Form(None),
    passcode_pattern: Optional[str] = Form(None),
    imei: Optional[str] = Form(None),
    reported_issue: str = Form(...),
    estimated_cost: Optional[str] = Form("0"),
    paid_amount: Optional[str] = Form("0"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    try:
        clean_estimated = max(0.0, float(estimated_cost)) if estimated_cost and str(estimated_cost).strip() else 0.0
    except ValueError:
        clean_estimated = 0.0
    try:
        clean_paid = max(0.0, float(paid_amount)) if paid_amount and str(paid_amount).strip() else 0.0
    except ValueError:
        clean_paid = 0.0

    # Find or create customer
    phone_clean = customer_phone.strip()
    customer = db.query(Customer).filter(Customer.phone == phone_clean).first()
    if not customer:
        customer = Customer(name=customer_name.strip(), phone=phone_clean)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    # Generate unique ticket code: REP-YYMMDD-XXXX
    ticket_code = _next_ticket_code(db)

    ticket = RepairTicket(
        ticket_code=ticket_code,
        customer_id=customer.id,
        technician_id=current_user.id if current_user.role == "technician" else None,
        device_brand=device_brand.strip(),
        device_model=device_model.strip(),
        color=color.strip() if color else None,
        passcode_pattern=passcode_pattern.strip() if passcode_pattern else None,
        imei=imei.strip() if imei else None,
        reported_issue=reported_issue.strip(),
        status="received",
        estimated_cost=clean_estimated,
        final_cost=clean_estimated,
        paid_amount=clean_paid
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return RedirectResponse(url=f"/repairs/{ticket.id}/print", status_code=303)

@router.get("/{ticket_id}", response_class=HTMLResponse)
def view_ticket(
    request: Request,
    ticket_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="تذكرة الصيانة غير موجودة")

    # Available spare parts from inventory (types where use_in_repairs is True)
    available_parts = db.query(Product).join(ProductType).filter(
        ProductType.use_in_repairs == True,
        Product.quantity > 0,
        Product.is_active == True,
        Product.is_archived == False
    ).order_by(Product.name.asc()).all()

    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="repairs/ticket_detail.html", context={
        "current_user": current_user,
        "active_page": "repairs",
        "ticket": ticket,
        "available_parts": available_parts,
        "currency": settings.currency if settings else "د.ل"
    })

@router.post("/{ticket_id}/add-part")
def add_spare_part_to_ticket(
    ticket_id: int,
    product_id: int = Form(...),
    quantity: int = Form(1),
    current_user: User = Depends(require_repairs_tech),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    product = db.query(Product).filter(Product.id == product_id).first()

    if not ticket or not product:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")

    if not product.product_type or not product.product_type.use_in_repairs:
        raise HTTPException(status_code=400, detail="هذا الصنف غير مخصص للاستخدام كقطع غيار")

    if product.quantity <= 0 or quantity <= 0:
        raise HTTPException(status_code=400, detail="القطعة المطلوبة غير متوفرة حالياً في المخزون")

    qty = 1 if product.is_unit else max(1, min(int(quantity), product.quantity))
    
    part = RepairPart(
        ticket_id=ticket.id,
        product_id=product.id,
        part_name=product.name,
        quantity=qty,
        cost_price=round(product.buy_price * qty, 2),
        price_charged=round(product.sell_price * qty, 2)
    )
    db.add(part)

    # Automatically deduct from inventory
    product.quantity = max(0, product.quantity - qty)

    # Recalculate ticket final cost
    ticket.final_cost = round(ticket.final_cost + (product.sell_price * qty), 2)
    db.commit()

    return RedirectResponse(url=f"/repairs/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/remove-part/{part_id}")
def remove_spare_part_from_ticket(
    ticket_id: int,
    part_id: int,
    current_user: User = Depends(require_repairs_tech),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    part = db.query(RepairPart).filter(
        RepairPart.id == part_id,
        RepairPart.ticket_id == ticket_id
    ).first()

    if not ticket or not part:
        raise HTTPException(status_code=404, detail="قطعة الغيار أو التذكرة غير موجودة")

    # Restore stock to product
    product = db.query(Product).filter(Product.id == part.product_id).first()
    if product:
        if product.is_unit:
            product.quantity = 1
        else:
            product.quantity += part.quantity

    # Adjust ticket final cost
    ticket.final_cost = round(max(0.0, ticket.final_cost - part.price_charged), 2)
    db.delete(part)
    db.commit()

    return RedirectResponse(url=f"/repairs/{ticket_id}", status_code=303)


@router.post("/{ticket_id}/update-status")
def update_ticket_status(
    ticket_id: int,
    status: str = Form(...),
    repair_notes: Optional[str] = Form(None),
    final_cost: Optional[str] = Form("0"),
    paid_amount: Optional[str] = Form("0"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="التذكرة غير موجودة")

    try:
        clean_final_cost = max(0.0, float(final_cost)) if final_cost and str(final_cost).strip() else 0.0
    except ValueError:
        clean_final_cost = ticket.final_cost
    try:
        clean_paid_amount = max(0.0, float(paid_amount)) if paid_amount and str(paid_amount).strip() else 0.0
    except ValueError:
        clean_paid_amount = ticket.paid_amount

    ticket.status = status
    ticket.repair_notes = repair_notes.strip() if repair_notes is not None else ticket.repair_notes
    ticket.final_cost = clean_final_cost
    ticket.paid_amount = clean_paid_amount

    if status == "delivered" and not ticket.delivered_at:
        ticket.delivered_at = datetime.now()

    db.commit()
    return RedirectResponse(url=f"/repairs/{ticket_id}", status_code=303)

@router.get("/{ticket_id}/print", response_class=HTMLResponse)
def print_ticket_receipt(
    request: Request,
    ticket_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="التذكرة غير موجودة")

    settings = db.query(ShopSettings).first()
    return templates.TemplateResponse(request=request, name="repairs/ticket_print.html", context={
        "ticket": ticket,
        "settings": settings
    })
