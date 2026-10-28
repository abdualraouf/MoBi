import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

FIELD_KINDS = ("text", "number", "select", "boolean")

class ProductType(Base):
    __tablename__ = "product_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    icon = Column(String(16), default="📦", nullable=False)
    show_in_pos = Column(Boolean, default=True, nullable=False)
    use_in_repairs = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    attributes = relationship(
        "TypeAttribute",
        back_populates="product_type",
        cascade="all, delete-orphan",
        order_by="TypeAttribute.sort_order"
    )
    products = relationship("Product", back_populates="product_type")

    @property
    def unique_attributes(self):
        return [a for a in self.attributes if a.is_unique]

    @property
    def has_unique_attribute(self) -> bool:
        return any(a.is_unique for a in self.attributes)

    def __repr__(self):
        return f"<ProductType {self.name} ({self.icon})>"


class TypeAttribute(Base):
    __tablename__ = "type_attributes"

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("product_types.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    field_kind = Column(String(20), default="text", nullable=False)  # "text", "number", "select", "boolean"
    options = Column(Text, nullable=True)  # JSON list[str], only for "select"
    is_required = Column(Boolean, default=False, nullable=False)
    is_unique = Column(Boolean, default=False, nullable=False)
    show_on_receipt = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    product_type = relationship("ProductType", back_populates="attributes")
    values = relationship(
        "ProductAttributeValue",
        back_populates="attribute",
        cascade="all, delete-orphan"
    )

    @property
    def options_list(self) -> list[str]:
        try:
            return json.loads(self.options) if self.options else []
        except (ValueError, TypeError):
            return []

    def __repr__(self):
        return f"<TypeAttribute {self.name} ({self.field_kind}) for Type #{self.type_id}>"
