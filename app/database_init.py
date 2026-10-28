import json
import sqlite3
import shutil
from datetime import datetime
from sqlalchemy.orm import Session
from app.config import DATABASE_PATH, SCHEMA_VERSION
from app.database import engine, SessionLocal, Base
from app.models import (
    User, ProductType, TypeAttribute, Tag, Product, ProductAttributeValue,
    AppMeta, Customer, ShopSettings
)
from app.services.auth_service import hash_password

def _ensure_schema_version():
    """If an existing DB has an older/unknown schema, back it up and start fresh."""
    if not DATABASE_PATH.exists() or DATABASE_PATH.stat().st_size == 0:
        return

    current = None
    try:
        con = sqlite3.connect(str(DATABASE_PATH))
        try:
            row = con.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()
            current = int(row[0]) if row else None
        except sqlite3.Error:
            current = None  # Table missing -> legacy v1 schema
        finally:
            con.close()
    except Exception as e:
        print(f"[MIGRATION CHECK WARNING] Could not read SQLite schema version: {e}")
        current = None

    if current == SCHEMA_VERSION:
        return

    engine.dispose()  # Release file locks before renaming
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATABASE_PATH.with_name(f"{DATABASE_PATH.name}.bak-{stamp}")
    shutil.move(str(DATABASE_PATH), str(backup))
    print(f"[MIGRATION] Old schema (v{current}) backed up to {backup.name}; creating fresh v{SCHEMA_VERSION} database.")


def init_db():
    """Create all tables and seed initial essential data if database is brand new."""
    _ensure_schema_version()
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        # 0. Ensure App Metadata (Schema version and barcode sequence)
        meta_ver = db.query(AppMeta).filter(AppMeta.key == "schema_version").first()
        if not meta_ver:
            db.add(AppMeta(key="schema_version", value=str(SCHEMA_VERSION)))
        else:
            meta_ver.value = str(SCHEMA_VERSION)

        meta_seq = db.query(AppMeta).filter(AppMeta.key == "barcode_seq").first()
        if not meta_seq:
            db.add(AppMeta(key="barcode_seq", value="0"))
        db.commit()

        # 1. Ensure Default Users exist
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                full_name="مدير النظام",
                hashed_password=hash_password("admin123"),
                role="admin",
                is_active=True
            )
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
            db.add_all([admin_user, cashier_user, technician_user])
            db.commit()

        # 2. Ensure Shop Settings exist
        settings = db.query(ShopSettings).first()
        if not settings:
            settings = ShopSettings(
                shop_name="MoBi لخدمات ومبيعات الهواتف",
                phone="0500123456",
                secondary_phone="0112345678",
                address="الشارع العام - مجمع الاتصالات",
                currency="د.ل",
                thermal_width="80mm"
            )
            db.add(settings)
            db.commit()

        # 3. Ensure Default Product Types and Attributes exist
        if db.query(ProductType).count() == 0:
            types_seed = [
                {
                    "name": "هواتف",
                    "icon": "📱",
                    "show_in_pos": True,
                    "use_in_repairs": False,
                    "sort_order": 10,
                    "attributes": [
                        {"name": "IMEI", "field_kind": "text", "is_required": True, "is_unique": True, "show_on_receipt": True, "sort_order": 10},
                        {"name": "اللون", "field_kind": "select", "options": json.dumps(["أسود", "أبيض", "أزرق", "ذهبي", "تيتانيوم طبيعي", "تيتانيوم أسود"], ensure_ascii=False), "is_required": False, "is_unique": False, "show_on_receipt": True, "sort_order": 20},
                        {"name": "السعة", "field_kind": "select", "options": json.dumps(["64GB", "128GB", "256GB", "512GB", "1TB"], ensure_ascii=False), "is_required": False, "is_unique": False, "show_on_receipt": True, "sort_order": 30},
                        {"name": "الحالة", "field_kind": "select", "options": json.dumps(["جديد", "مستعمل"], ensure_ascii=False), "is_required": False, "is_unique": False, "show_on_receipt": True, "sort_order": 40},
                    ]
                },
                {
                    "name": "شواحن وكابلات",
                    "icon": "🔌",
                    "show_in_pos": True,
                    "use_in_repairs": False,
                    "sort_order": 20,
                    "attributes": [
                        {"name": "القدرة (W)", "field_kind": "number", "is_required": False, "is_unique": False, "show_on_receipt": False, "sort_order": 10},
                        {"name": "نوع المنفذ", "field_kind": "select", "options": json.dumps(["Type-C", "Lightning", "Micro USB"], ensure_ascii=False), "is_required": False, "is_unique": False, "show_on_receipt": False, "sort_order": 20},
                    ]
                },
                {
                    "name": "حمايات وكفرات",
                    "icon": "🛡️",
                    "show_in_pos": True,
                    "use_in_repairs": False,
                    "sort_order": 30,
                    "attributes": [
                        {"name": "الموديل المتوافق", "field_kind": "text", "is_required": False, "is_unique": False, "show_on_receipt": False, "sort_order": 10},
                    ]
                },
                {
                    "name": "سماعات وملحقات",
                    "icon": "🎧",
                    "show_in_pos": True,
                    "use_in_repairs": False,
                    "sort_order": 40,
                    "attributes": []
                },
                {
                    "name": "بطاريات",
                    "icon": "🔋",
                    "show_in_pos": True,
                    "use_in_repairs": True,
                    "sort_order": 50,
                    "attributes": [
                        {"name": "السعة (mAh)", "field_kind": "number", "is_required": False, "is_unique": False, "show_on_receipt": False, "sort_order": 10},
                    ]
                },
                {
                    "name": "شاشات",
                    "icon": "📲",
                    "show_in_pos": False,
                    "use_in_repairs": True,
                    "sort_order": 60,
                    "attributes": [
                        {"name": "الموديل المتوافق", "field_kind": "text", "is_required": False, "is_unique": False, "show_on_receipt": False, "sort_order": 10},
                    ]
                },
                {
                    "name": "قطع غيار صيانة",
                    "icon": "🛠️",
                    "show_in_pos": False,
                    "use_in_repairs": True,
                    "sort_order": 70,
                    "attributes": []
                },
            ]

            type_map = {}
            for t_data in types_seed:
                attrs = t_data.pop("attributes")
                pt = ProductType(**t_data)
                db.add(pt)
                db.flush()
                for a_data in attrs:
                    db.add(TypeAttribute(type_id=pt.id, **a_data))
                db.flush()
                type_map[pt.name] = pt
            db.commit()

        # 4. Ensure Default Tags exist
        if db.query(Tag).count() == 0:
            tags_seed = [
                {"name": "Apple", "color": "blue", "show_on_shelf": True, "sort_order": 10},
                {"name": "Samsung", "color": "cyan", "show_on_shelf": True, "sort_order": 20},
                {"name": "Anker", "color": "emerald", "show_on_shelf": True, "sort_order": 30},
                {"name": "Xiaomi", "color": "amber", "show_on_shelf": False, "sort_order": 40},
            ]
            tag_map = {}
            for tag_data in tags_seed:
                t = Tag(**tag_data)
                db.add(t)
                db.flush()
                tag_map[t.name] = t
            db.commit()

        # 5. Ensure Default Walk-in Customer exists
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

        # 6. Seed Initial Products (if no products exist)
        if db.query(Product).count() == 0:
            types = {t.name: t for t in db.query(ProductType).all()}
            tags = {t.name: t for t in db.query(Tag).all()}

            def get_attr(pt_name, attr_name):
                pt = types[pt_name]
                for a in pt.attributes:
                    if a.name == attr_name:
                        return a
                return None

            # 1. Charger
            p_charger = Product(
                type_id=types["شواحن وكابلات"].id,
                name="شاحن سريع Anker 20W Type-C",
                barcode="6934177701234",
                buy_price=35.0,
                sell_price=55.0,
                min_sell_price=50.0,
                quantity=25,
                alert_quantity=5,
                unit="قطعة",
                sort_order=10
            )
            p_charger.tags.append(tags["Anker"])
            db.add(p_charger)
            db.flush()

            a_power = get_attr("شواحن وكابلات", "القدرة (W)")
            a_port = get_attr("شواحن وكابلات", "نوع المنفذ")
            if a_power:
                db.add(ProductAttributeValue(product_id=p_charger.id, attribute_id=a_power.id, value="20"))
            if a_port:
                db.add(ProductAttributeValue(product_id=p_charger.id, attribute_id=a_port.id, value="Type-C"))

            # 2. Cable
            p_cable = Product(
                type_id=types["شواحن وكابلات"].id,
                name="كيبل آيفون لايتنينج أصلي 1M",
                barcode="190198496245",
                buy_price=40.0,
                sell_price=70.0,
                min_sell_price=65.0,
                quantity=18,
                alert_quantity=4,
                unit="قطعة",
                sort_order=20
            )
            p_cable.tags.append(tags["Apple"])
            db.add(p_cable)
            db.flush()
            if a_port:
                db.add(ProductAttributeValue(product_id=p_cable.id, attribute_id=a_port.id, value="Lightning"))

            # 3. iPhone Unit 1
            p_iphone1 = Product(
                type_id=types["هواتف"].id,
                name="Apple iPhone 15 Pro",
                barcode="IP15P-0001",
                buy_price=3800.0,
                sell_price=4250.0,
                min_sell_price=4150.0,
                quantity=1,
                alert_quantity=1,
                unit="جهاز",
                sort_order=30
            )
            p_iphone1.tags.append(tags["Apple"])
            db.add(p_iphone1)
            db.flush()

            a_imei = get_attr("هواتف", "IMEI")
            a_color = get_attr("هواتف", "اللون")
            a_storage = get_attr("هواتف", "السعة")
            a_condition = get_attr("هواتف", "الحالة")
            if a_imei:
                db.add(ProductAttributeValue(product_id=p_iphone1.id, attribute_id=a_imei.id, value="354892091234567"))
            if a_color:
                db.add(ProductAttributeValue(product_id=p_iphone1.id, attribute_id=a_color.id, value="تيتانيوم طبيعي"))
            if a_storage:
                db.add(ProductAttributeValue(product_id=p_iphone1.id, attribute_id=a_storage.id, value="256GB"))
            if a_condition:
                db.add(ProductAttributeValue(product_id=p_iphone1.id, attribute_id=a_condition.id, value="جديد"))

            # 4. iPhone Unit 2
            p_iphone2 = Product(
                type_id=types["هواتف"].id,
                name="Apple iPhone 15 Pro",
                barcode="IP15P-0002",
                buy_price=3400.0,
                sell_price=3850.0,
                min_sell_price=3750.0,
                quantity=1,
                alert_quantity=1,
                unit="جهاز",
                sort_order=40
            )
            p_iphone2.tags.append(tags["Apple"])
            db.add(p_iphone2)
            db.flush()
            if a_imei:
                db.add(ProductAttributeValue(product_id=p_iphone2.id, attribute_id=a_imei.id, value="354892097654321"))
            if a_color:
                db.add(ProductAttributeValue(product_id=p_iphone2.id, attribute_id=a_color.id, value="تيتانيوم أسود"))
            if a_storage:
                db.add(ProductAttributeValue(product_id=p_iphone2.id, attribute_id=a_storage.id, value="128GB"))
            if a_condition:
                db.add(ProductAttributeValue(product_id=p_iphone2.id, attribute_id=a_condition.id, value="جديد"))

            # 5. Battery
            p_battery = Product(
                type_id=types["بطاريات"].id,
                name="بطارية Samsung A54 أصلية",
                barcode="BAT-A54",
                buy_price=60.0,
                sell_price=110.0,
                min_sell_price=95.0,
                quantity=6,
                alert_quantity=2,
                unit="بطارية",
                sort_order=50
            )
            p_battery.tags.append(tags["Samsung"])
            db.add(p_battery)
            db.flush()
            a_mah = get_attr("بطاريات", "السعة (mAh)")
            if a_mah:
                db.add(ProductAttributeValue(product_id=p_battery.id, attribute_id=a_mah.id, value="5000"))

            # 6. Screen
            p_screen = Product(
                type_id=types["شاشات"].id,
                name="شاشة Samsung Galaxy A54 5G أصلية",
                barcode="SP-A54-OLED",
                buy_price=160.0,
                sell_price=240.0,
                min_sell_price=220.0,
                quantity=8,
                alert_quantity=2,
                unit="شاشة",
                sort_order=60
            )
            p_screen.tags.append(tags["Samsung"])
            db.add(p_screen)
            db.flush()
            a_compat = get_attr("شاشات", "الموديل المتوافق")
            if a_compat:
                db.add(ProductAttributeValue(product_id=p_screen.id, attribute_id=a_compat.id, value="A54 5G"))

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
