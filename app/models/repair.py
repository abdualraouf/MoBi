from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class RepairTicket(Base):
    """
    Complete repair ticket lifecycle for the mobile maintenance workshop.
    Barcode is generated from ticket_code for printable stickers and customer receipts.
    """
    __tablename__ = "repair_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_code = Column(String(50), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Device Details
    device_brand = Column(String(50), nullable=False)  # سامسونج، آبل، شاومي، هواوي
    device_model = Column(String(100), nullable=False)
    imei = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    passcode_pattern = Column(String(100), nullable=True)  # الرمز السري أو النمط

    # Issue & Status
    reported_issue = Column(String(255), nullable=False)  # وصف العطل
    initial_diagnosis = Column(String(255), nullable=True)  # فحص الاستلام
    repair_notes = Column(String(500), nullable=True)  # تقرير الفني
    # Statuses: received (مستلم), diagnosing (قيد الفحص), waiting_parts (بانتظار القطع),
    # repairing (قيد الإصلاح), ready (جاهز للتسليم), delivered (تم التسليم), unrepairable (غير قابل للإصلاح)
    status = Column(String(30), default="received", nullable=False)

    # Financials
    estimated_cost = Column(Float, default=0.0, nullable=False)
    final_cost = Column(Float, default=0.0, nullable=False)
    paid_amount = Column(Float, default=0.0, nullable=False)
    warranty_days = Column(Integer, default=7, nullable=False)

    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="repairs")
    technician = relationship("User", back_populates="assigned_repairs")
    parts = relationship("RepairPart", back_populates="ticket", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RepairTicket {self.ticket_code} - {self.device_model} ({self.status})>"


class RepairPart(Base):
    """
    Tracks spare parts consumed from inventory for a specific repair ticket.
    Automatically deducted from product quantity upon adding.
    """
    __tablename__ = "repair_parts"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("repair_tickets.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    part_name = Column(String(150), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    cost_price = Column(Float, default=0.0, nullable=False)
    price_charged = Column(Float, default=0.0, nullable=False)

    # Relationships
    ticket = relationship("RepairTicket", back_populates="parts")
    product = relationship("Product", back_populates="repair_parts")

    def __repr__(self):
        return f"<RepairPart {self.part_name} x{self.quantity}>"
