from sqlalchemy.orm import Session
from app.database import engine, SessionLocal, Base
from app.models import (
    User, Category, Product, ProductItem, Customer, ShopSettings
)
from app.services.auth_service import hash_password

def init_db():
    """Create all tables and seed initial essential data if database is brand new."""
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        # 1. Ensure Default Admin User exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                full_name="مدير النظام",
                hashed_password=hash_password("admin123"),
                role="admin",
                is_active=True
            )
            db.add(admin_user)

            # Also create sample cashier & technician accounts for testing
            cashier_user = User(
                username="cashier",
                full_name="كاشير المبيعات",
                hashed_password=hash_password("cashier123"),
                role="cashier",
                is_active=True
            )
            technician_user = User(
                username="tech",
                full_name="فني الصيانة",
                hashed_password=hash_password("tech123"),
                role="technician",
                is_active=True
            )
            db.add_all([cashier_user, technician_user])
            db.commit()

        # 2. Ensure Shop Settings exist
        settings = db.query(ShopSettings).first()
        if not settings:
            settings = ShopSettings(
                shop_name="MoBi لخدمات ومبيعات الهواتف",
                phone="0500123456",
                secondary_phone="0112345678",
                address="الشارع العام - مجمع الاتصالات",
                currency="ر.س",
                thermal_width="80mm"
            )
            db.add(settings)
            db.commit()

        # 3. Ensure Default Categories exist
        default_categories = [
            {"name": "هواتف ذكية", "type": "phone", "description": "هواتف جديدة ومستعملة مع تتبع IMEI"},
            {"name": "شواحن وكابلات", "type": "accessory", "description": "شواحن جدارية، كوابل، وشواحن سيارة"},
            {"name": "حمايات وكفرات", "type": "accessory", "description": "زجاج حماية، استيكرات، أغطية حماية"},
            {"name": "سماعات وملحقات", "type": "accessory", "description": "سماعات بلوتوث، باور بانك، إكسسوارات"},
            {"name": "شاشات وبطاريات", "type": "spare_part", "description": "شاشات أصلية وتجارية، بطاريات هواتف"},
            {"name": "قطع غيار صيانة", "type": "spare_part", "description": "فلاتات، منافذ شحن، كاميرات، أيسيهات"}
        ]

        category_map = {}
        for cat_data in default_categories:
            existing = db.query(Category).filter(Category.name == cat_data["name"]).first()
            if not existing:
                existing = Category(**cat_data)
                db.add(existing)
                db.commit()
                db.refresh(existing)
            category_map[existing.name] = existing

        # 4. Ensure Default Walk-in Customer exists
        default_customer = db.query(Customer).filter(Customer.phone == "0000000000").first()
        if not default_customer:
            default_customer = Customer(
                name="زبون نقدي (عام)",
                phone="0000000000",
                address="محلي",
                notes="عميل المبيعات النقدية السريعة"
            )
            db.add(default_customer)
            db.commit()

        # 5. Seed initial products if no products exist yet (Sample inventory)
        if db.query(Product).count() == 0:
            # Accessory with pre-printed barcode
            charger = Product(
                category_id=category_map["شواحن وكابلات"].id,
                name="شاحن سريع Anker 20W Type-C",
                barcode="6934177701234",
                brand="Anker",
                model="PowerPort III",
                buy_price=35.0,
                sell_price=55.0,
                min_sell_price=50.0,
                quantity=25,
                alert_quantity=5,
                has_imei=False,
                unit="قطعة"
            )
            cable = Product(
                category_id=category_map["شواحن وكابلات"].id,
                name="كيبل آيفون لايتنينج أصلي 1M",
                barcode="190198496245",
                brand="Apple",
                model="USB-C to Lightning",
                buy_price=40.0,
                sell_price=70.0,
                min_sell_price=65.0,
                quantity=18,
                alert_quantity=4,
                has_imei=False,
                unit="قطعة"
            )
            screen_part = Product(
                category_id=category_map["شاشات وبطاريات"].id,
                name="شاشة Samsung Galaxy A54 5G أصلية",
                barcode="SP-A54-OLED",
                brand="Samsung",
                model="A54 5G",
                buy_price=160.0,
                sell_price=240.0,
                min_sell_price=220.0,
                quantity=8,
                alert_quantity=2,
                has_imei=False,
                unit="شاشة"
            )
            # Mobile Phone with IMEI tracking
            iphone_phone = Product(
                category_id=category_map["هواتف ذكية"].id,
                name="Apple iPhone 15 Pro",
                barcode="IPHONE-15PRO-BASE",
                brand="Apple",
                model="iPhone 15 Pro",
                buy_price=3800.0,
                sell_price=4250.0,
                min_sell_price=4150.0,
                quantity=2,
                alert_quantity=1,
                has_imei=True,
                unit="جهاز"
            )
            db.add_all([charger, cable, screen_part, iphone_phone])
            db.commit()
            db.refresh(iphone_phone)

            # Add two specific IMEI units for the phone
            item1 = ProductItem(
                product_id=iphone_phone.id,
                imei="354892091234567",
                imei2="354892091234568",
                color="تيتانيوم طبيعي",
                storage="256GB",
                condition="new",
                status="in_stock",
                buy_price=3800.0,
                sell_price=4250.0
            )
            item2 = ProductItem(
                product_id=iphone_phone.id,
                imei="354892097654321",
                imei2="354892097654322",
                color="تيتانيوم أسود",
                storage="128GB",
                condition="new",
                status="in_stock",
                buy_price=3400.0,
                sell_price=3850.0
            )
            db.add_all([item1, item2])
            db.commit()

        print("[OK] MoBi Database initialized and seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Database initialization error: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
