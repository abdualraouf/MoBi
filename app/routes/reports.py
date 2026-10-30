from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.template_engine import templates
from app.database import get_db
from app.models.invoice import Invoice, InvoiceItem
from app.models.repair import RepairTicket
from app.models.settings import ShopSettings
from app.models.user import User
from app.routes.auth import require_user

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("", response_class=HTMLResponse)
def view_reports(
    request: Request,
    period: str = "today",
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="هذه الشاشة مخصصة لمدير النظام فقط")

    now = datetime.now()
    query_invoices = db.query(Invoice)
    query_repairs = db.query(RepairTicket)

    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query_invoices = query_invoices.filter(Invoice.created_at >= start_date)
        query_repairs = query_repairs.filter(RepairTicket.received_at >= start_date)
    elif period == "week":
        start_date = now - timedelta(days=7)
        query_invoices = query_invoices.filter(Invoice.created_at >= start_date)
        query_repairs = query_repairs.filter(RepairTicket.received_at >= start_date)
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query_invoices = query_invoices.filter(Invoice.created_at >= start_date)
        query_repairs = query_repairs.filter(RepairTicket.received_at >= start_date)

    invoices = query_invoices.order_by(Invoice.id.desc()).all()
    repairs = query_repairs.all()

    total_sales = sum(inv.total_amount for inv in invoices)
    sales_cash = sum(inv.paid_amount for inv in invoices if inv.payment_method == "cash")
    
    # Calculate profit from invoice items: (unit_price - buy_price) * quantity
    invoice_ids = [inv.id for inv in invoices]
    sales_profit = 0.0
    if invoice_ids:
        items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id.in_(invoice_ids)).all()
        sales_profit = sum((item.unit_price - item.buy_price) * item.quantity for item in items)
        # Minus overall invoice discounts
        total_discounts = sum(inv.discount for inv in invoices)
        sales_profit = max(0.0, sales_profit - total_discounts)

    repair_revenue = sum(rep.paid_amount for rep in repairs)
    repair_parts_cost = sum(part.cost_price for rep in repairs for part in rep.parts)
    repair_profit = max(0.0, repair_revenue - repair_parts_cost)

    net_profit = round(sales_profit + repair_profit, 2)
    cash_collected = round(sales_cash + repair_revenue, 2)

    stats = {
        "total_sales": round(total_sales, 2),
        "sales_profit": round(sales_profit, 2),
        "repair_profit": round(repair_profit, 2),
        "net_profit": net_profit,
        "repair_revenue": round(repair_revenue, 2),
        "cash_collected": cash_collected,
        "invoices_count": len(invoices),
        "repairs_count": len(repairs)
    }

    settings = db.query(ShopSettings).first()

    return templates.TemplateResponse(request=request, name="reports/index.html", context={
        "current_user": current_user,
        "active_page": "reports",
        "period": period,
        "stats": stats,
        "invoices": invoices,
        "currency": settings.currency if settings else "د.ل"
    })
