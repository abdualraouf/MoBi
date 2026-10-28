from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base

class ProductAttributeValue(Base):
    __tablename__ = "product_attribute_values"
    __table_args__ = (
        UniqueConstraint("product_id", "attribute_id", name="uq_product_attribute"),
        Index("ix_attr_value_lookup", "attribute_id", "value"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    attribute_id = Column(Integer, ForeignKey("type_attributes.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(255), nullable=False)

    product = relationship("Product", back_populates="attribute_values")
    attribute = relationship("TypeAttribute", back_populates="values")

    def __repr__(self):
        return f"<ProductAttributeValue Prod #{self.product_id} Attr #{self.attribute_id}='{self.value}'>"
