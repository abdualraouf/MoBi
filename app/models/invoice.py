from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subtotal = Column(Float, default=0.0, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
    total_amount = Column(Float, default=0.0, nullable=False)
    paid_amount = Column(Float, default=0.0, nullable=False)
    remaining_amount = Column(Float, default=0.0, nullable=False)
    payment_method = Column(String(30), default="cash", nullable=False)  # "cash", "card", "transfer", "debt"
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    cashier = relationship("User", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    sold_items = relationship("ProductItem", back_populates="invoice")

    def __repr__(self):
        return f"<Invoice {self.invoice_number} - Total: {self.total_amount}>"


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product_item_id = Column(Integer, ForeignKey("product_items.id"), nullable=True)
    product_name = Column(String(150), nullable=False)  # Snapshot
    imei = Column(String(50), nullable=True)  # Snapshot for thermal receipt
    quantity = Column(Integer, default=1, nullable=False)
    buy_price = Column(Float, default=0.0, nullable=False)  # Profit calculation
    unit_price = Column(Float, default=0.0, nullable=False)
    total_price = Column(Float, default=0.0, nullable=False)

    # Relationships
    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="invoice_items")
    product_item = relationship("ProductItem")

    def __repr__(self):
        return f"<InvoiceItem {self.product_name} x{self.quantity}>"
