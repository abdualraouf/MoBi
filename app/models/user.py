from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="cashier", nullable=False)  # admin, cashier, technician
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    invoices = relationship("Invoice", back_populates="cashier")
    assigned_repairs = relationship("RepairTicket", back_populates="technician")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
