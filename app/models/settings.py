from sqlalchemy import Column, Integer, String, Text
from app.database import Base

class ShopSettings(Base):
    """
    Configuration and store profile for thermal receipts, currency, and repair terms.
    """
    __tablename__ = "shop_settings"

    id = Column(Integer, primary_key=True, index=True)
    shop_name = Column(String(150), default="MoBi لخدمات ومبيعات الهواتف", nullable=False)
    phone = Column(String(50), default="0500000000", nullable=False)
    secondary_phone = Column(String(50), nullable=True)
    address = Column(String(200), default="الشارع العام - مجمع الهواتف", nullable=False)
    currency = Column(String(20), default="ر.س", nullable=False)
    tax_number = Column(String(50), nullable=True)
    thermal_width = Column(String(10), default="80mm", nullable=False)  # "80mm" or "58mm"
    
    invoice_footer = Column(
        Text,
        default="شكراً لتعاملكم معنا. الأجهزة المباعة تستبدل خلال 3 أيام وتسترجع خلال 24 ساعة بشرط حالتها الأصلية والكرتونة.",
        nullable=False
    )
    
    repair_terms = Column(
        Text,
        default="1. المحل غير مسؤول عن البيانات المخزنة بالجهاز أثناء الفحص والإصلاح.\n2. الأجهزة المتروكة لأكثر من 30 يوماً بعد إشعار الجاهزية يحق للمحل التصرف بها لتغطية التكاليف.\n3. الضمان يشمل قطعة الغيار المستبدلة فقط لمدة 7 أيام ولا يشمل سوء الاستخدام أو السوائل.",
        nullable=False
    )

    logo_path = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<ShopSettings {self.shop_name}>"
