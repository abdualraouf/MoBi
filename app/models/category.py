from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    # Types: "phone" (هواتف), "accessory" (إكسسوارات), "spare_part" (قطع غيار)
    type = Column(String(50), nullable=False, default="accessory")
    description = Column(String(255), nullable=True)

    # Relationships
    products = relationship("Product", back_populates="category")

    def __repr__(self):
        return f"<Category {self.name} ({self.type})>"
