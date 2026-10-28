from sqlalchemy import Column, String
from app.database import Base

class AppMeta(Base):
    __tablename__ = "app_meta"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)

    def __repr__(self):
        return f"<AppMeta {self.key}={self.value}>"
