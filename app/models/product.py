from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("product_types.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    barcode = Column(String(100), unique=True, index=True, nullable=False)
    buy_price = Column(Float, default=0.0, nullable=False)
    sell_price = Column(Float, default=0.0, nullable=False)
    min_sell_price = Column(Float, default=0.0, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    alert_quantity = Column(Integer, default=3, nullable=False)
    unit = Column(String(50), default="قطعة", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    @hybrid_property
    def is_archived(self) -> bool:
        return not self.is_active

    @is_archived.setter
    def is_archived(self, value: bool):
        self.is_active = not value

    @is_archived.expression
    def is_archived(cls):
        return cls.is_active == False

    # Relationships
    product_type = relationship("ProductType", back_populates="products")
    tags = relationship("Tag", secondary="product_tags", back_populates="products")
    attribute_values = relationship(
        "ProductAttributeValue",
        back_populates="product",
        cascade="all, delete-orphan"
    )
    invoice_items = relationship("InvoiceItem", back_populates="product")
    repair_parts = relationship("RepairPart", back_populates="product")

    @property
    def is_unit(self) -> bool:
        """True if product's type has a unique attribute -> quantity locked to 0/1."""
        return self.product_type.has_unique_attribute if self.product_type else False

    def attr_map(self) -> dict[int, str]:
        return {v.attribute_id: v.value for v in self.attribute_values}

    @property
    def display_attributes(self) -> list[dict]:
        """Ordered [{'name': str, 'value': str, 'is_unique': bool, 'show_on_receipt': bool}] following TypeAttribute.sort_order."""
        if not self.product_type:
            return []
        values = self.attr_map()
        out = []
        for a in self.product_type.attributes:
            if a.id in values and values[a.id] != "":
                out.append({
                    "name": a.name,
                    "value": values[a.id],
                    "is_unique": a.is_unique,
                    "show_on_receipt": a.show_on_receipt
                })
        return out

    @property
    def primary_unique_value(self) -> str | None:
        if not self.product_type:
            return None
        values = self.attr_map()
        for a in self.product_type.attributes:
            if a.is_unique:
                val = values.get(a.id)
                if val:
                    return val
        return None

    @property
    def is_sellable(self) -> bool:
        return (
            self.is_active
            and self.product_type is not None
            and not self.product_type.is_archived
            and self.product_type.show_in_pos
        )

    def __repr__(self):
        return f"<Product {self.name} (Barcode: {self.barcode})>"
