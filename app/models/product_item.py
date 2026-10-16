from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class ProductItem(Base):
    """
    Represents an individual physical phone unit uniquely tracked by its IMEI number.
    Essential for mobile shops dealing with new and pre-owned devices.
    """
    __tablename__ = "product_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    imei = Column(String(50), unique=True, index=True, nullable=False)
    imei2 = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    storage = Column(String(50), nullable=True)  # e.g., "128GB", "256GB"
    condition = Column(String(20), default="new", nullable=False)  # "new", "used"
    battery_health = Column(String(20), nullable=True)  # e.g., "100%", "89%"
    status = Column(String(30), default="in_stock", nullable=False)  # "in_stock", "sold", "in_repair", "returned"
    buy_price = Column(Float, nullable=True)  # Specific purchase cost for used phones
    sell_price = Column(Float, nullable=True)  # Specific price
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)

    # Relationships
    product = relationship("Product", back_populates="items")
    invoice = relationship("Invoice", back_populates="sold_items")

    def __repr__(self):
        return f"<ProductItem IMEI: {self.imei} ({self.status})>"
