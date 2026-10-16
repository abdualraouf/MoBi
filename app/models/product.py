from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(150), nullable=False, index=True)
    # The pre-printed manufacturer barcode (UPC/EAN) or custom generated code
    barcode = Column(String(100), unique=True, index=True, nullable=True)
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    buy_price = Column(Float, default=0.0, nullable=False)
    sell_price = Column(Float, default=0.0, nullable=False)
    min_sell_price = Column(Float, default=0.0, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)  # For accessories & spare parts
    alert_quantity = Column(Integer, default=3, nullable=False)  # Low stock threshold
    has_imei = Column(Boolean, default=False, nullable=False)  # True for mobile phones
    unit = Column(String(50), default="قطعة", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    category = relationship("Category", back_populates="products")
    items = relationship("ProductItem", back_populates="product", cascade="all, delete-orphan")
    invoice_items = relationship("InvoiceItem", back_populates="product")
    repair_parts = relationship("RepairPart", back_populates="product")

    def __repr__(self):
        return f"<Product {self.name} (Barcode: {self.barcode})>"
