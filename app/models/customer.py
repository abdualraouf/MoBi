from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(30), unique=True, index=True, nullable=False)
    national_id = Column(String(50), nullable=True)
    address = Column(String(200), nullable=True)
    notes = Column(String(255), nullable=True)
    balance = Column(Float, default=0.0, nullable=False)  # Positive = credit, Negative = debt
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    invoices = relationship("Invoice", back_populates="customer")
    repairs = relationship("RepairTicket", back_populates="customer")

    def __repr__(self):
        return f"<Customer {self.name} ({self.phone})>"
