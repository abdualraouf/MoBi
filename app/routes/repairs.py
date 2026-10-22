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
from app.models.category import Category
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user

router = APIRouter(prefix="/repairs", tags=["repairs"])

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
    estimated_cost: float = Form(0.0),
    paid_amount: float = Form(0.0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # Find or create customer
    phone_clean = customer_phone.strip()
    customer = db.query(Customer).filter(Customer.phone == phone_clean).first()
    if not customer:
        customer = Customer(name=customer_name.strip(), phone=phone_clean)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    # Generate unique ticket code: REP-YYMMDD-XXXX
    date_str = datetime.utcnow().strftime("%y%m%d")
    today_count = db.query(RepairTicket).filter(RepairTicket.received_at >= datetime.utcnow().date()).count() + 1
    ticket_code = f"REP-{date_str}-{today_count:04d}"

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
        estimated_cost=estimated_cost,
        final_cost=estimated_cost,
        paid_amount=paid_amount
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

    # Available spare parts from inventory
    available_parts = db.query(Product).join(Category).filter(
        Category.type == "spare_part",
        Product.quantity > 0,
        Product.is_active == True
    ).all()

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
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    product = db.query(Product).filter(Product.id == product_id).first()

    if not ticket or not product:
        raise HTTPException(status_code=404, detail="البيانات غير موجودة")

    qty = max(1, min(quantity, product.quantity))
    
    part = RepairPart(
        ticket_id=ticket.id,
        product_id=product.id,
        part_name=product.name,
        quantity=qty,
        cost_price=product.buy_price * qty,
        price_charged=product.sell_price * qty
    )
    db.add(part)

    # Automatically deduct from inventory
    product.quantity = max(0, product.quantity - qty)

    # Recalculate ticket final cost
    ticket.final_cost += (product.sell_price * qty)
    db.commit()

    return RedirectResponse(url=f"/repairs/{ticket_id}", status_code=303)

@router.post("/{ticket_id}/update-status")
def update_ticket_status(
    ticket_id: int,
    status: str = Form(...),
    repair_notes: Optional[str] = Form(None),
    final_cost: float = Form(0.0),
    paid_amount: float = Form(0.0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(RepairTicket).filter(RepairTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="التذكرة غير موجودة")

    ticket.status = status
    ticket.repair_notes = repair_notes.strip() if repair_notes else ticket.repair_notes
    ticket.final_cost = final_cost
    ticket.paid_amount = paid_amount

    if status == "delivered" and not ticket.delivered_at:
        ticket.delivered_at = datetime.utcnow()

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
