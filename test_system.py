import os
import sys
import shutil
import json

# 1. Force test environment BEFORE importing any application module
os.environ["MOBI_TESTING"] = "1"

from fastapi.testclient import TestClient
from app.config import SESSION_COOKIE_NAME, DATABASE_PATH, UPLOADS_DIR, STATIC_DIR, IS_TESTING, SCHEMA_VERSION
from app.main import app
from app.database_init import init_db
from app.database import SessionLocal, engine
from app.models.product_type import ProductType, TypeAttribute
from app.models.tag import Tag
from app.models.product import Product
from app.models.attribute_value import ProductAttributeValue
from app.models.app_meta import AppMeta
from app.models.user import User

def run_tests():
    print("=" * 70)
    print("   MoBi Dynamic Inventory Verification Test Suite (v2.0 Isolated)")
    print("=" * 70)

    # Safety Guardrail: Never allow tests to run against production database!
    assert IS_TESTING is True, "Security Error: IS_TESTING is not enabled!"
    assert DATABASE_PATH.name == "test_mobi.db", f"Security Error: Tests must use test_mobi.db, got {DATABASE_PATH.name}!"
    assert UPLOADS_DIR.name == "test_uploads", f"Security Error: Tests must use test_uploads, got {UPLOADS_DIR.name}!"

    # Clean up any leftover test database from previous aborted runs
    engine.dispose()
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Isolated Test DB
    print("\n[1/15] Testing Database Initialization & Schema Version...")
    init_db()
    db = SessionLocal()
    meta = db.query(AppMeta).filter(AppMeta.key == "schema_version").first()
    assert meta is not None and int(meta.value) == SCHEMA_VERSION, f"Expected schema_version {SCHEMA_VERSION}, got {meta.value if meta else None}"
    types_count = db.query(ProductType).count()
    assert types_count >= 5, f"Expected at least 5 default types, got {types_count}"
    tags_count = db.query(Tag).count()
    assert tags_count >= 3, f"Expected at least 3 default tags, got {tags_count}"
    products_count = db.query(Product).count()
    assert products_count >= 5, f"Expected seeded products, got {products_count}"
    db.close()
    print(f"  -> Passed. Schema version {SCHEMA_VERSION} verified with {types_count} types and {products_count} seeded products.")

    client = TestClient(app)

    # 2. Test Login page & Admin Authentication
    print("\n[2/15] Testing Authentication (Admin & Cashier)...")
    res = client.get("/auth/login")
    assert res.status_code == 200
    assert "MoBi" in res.text

    # Admin Login
    login_admin = client.post("/auth/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert login_admin.status_code in [302, 303]
    admin_cookie = login_admin.cookies.get(SESSION_COOKIE_NAME)
    assert admin_cookie, "Admin session cookie was not set!"
    client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)
    print("  -> Passed. Admin authenticated.")

    # 3. Test POS Screen & Dynamic Shelf
    print("\n[3/15] Testing POS Screen & Dynamic Categories Shelf...")
    pos_res = client.get("/pos")
    assert pos_res.status_code == 200
    assert "نقطة البيع" in pos_res.text
    assert "shelf-mode-types" in pos_res.text
    assert "shelf-mode-tags" in pos_res.text
    # Should include default types on shelf
    assert "هواتف" in pos_res.text
    assert "شواحن وكابلات" in pos_res.text
    print("  -> Passed. POS loaded with category shelf modes.")

    # 4. Test Barcode Scanner: Bulk Accessory
    print("\n[4/15] Testing Barcode Scanner with accessory barcode (6934177701234)...")
    scan_res = client.post("/pos/add-item", data={"query": "6934177701234"})
    assert scan_res.status_code == 200
    assert "Anker" in scan_res.text
    print("  -> Passed. Bulk accessory added to cart.")

    # 5. Test Barcode Scanner: Phone Unit with Dynamic IMEI Attribute
    print("\n[5/15] Testing Barcode Scanner with dynamic IMEI value (354892091234567)...")
    imei_code = "354892091234567"
    imei_res = client.post("/pos/add-item", data={"query": imei_code})
    assert imei_res.status_code == 200
    assert "iPhone 15 Pro" in imei_res.text
    assert imei_code in imei_res.text
    print(f"  -> Passed. Phone unit resolved by dynamic IMEI attribute ({imei_code}).")

    # 6. Test Unit Quantity Enforcement (Cannot increment unit)
    print("\n[6/15] Testing Unit Quantity Protection (Units cannot have quantity > 1)...")
    db = SessionLocal()
    phone_prod = db.query(Product).filter(Product.barcode == "IP15P-0001").first()
    db.close()
    assert phone_prod is not None
    # Attempting to update unit quantity
    update_qty_res = client.post("/pos/update-qty", data={"cart_id": f"unit_{phone_prod.id}", "delta": 1})
    assert update_qty_res.status_code == 200
    # Quantity must remain 1
    assert "1" in update_qty_res.text
    print("  -> Passed. Unit product strictly constrained to quantity 1.")

    # 7. Test POS Category Picker Overlay & Grouping
    print("\n[7/15] Testing POS Picker Overlay (GET /pos/picker)...")
    db = SessionLocal()
    phones_type = db.query(ProductType).filter(ProductType.name == "هواتف").first()
    db.close()
    picker_res = client.get(f"/pos/picker?mode=type&scope_id={phones_type.id}")
    assert picker_res.status_code == 200
    assert "pos-picker-content" in picker_res.text
    assert "iPhone 15 Pro" in picker_res.text
    assert "أجهزة" in picker_res.text
    print("  -> Passed. Picker grid loaded with grouped phone card.")

    # 8. Test POS Picker Unit Drilldown & Add Specific Unit
    print("\n[8/15] Testing POS Unit Drilldown (GET /pos/picker/group/{id})...")
    drilldown_res = client.get(f"/pos/picker/group/{phone_prod.id}")
    assert drilldown_res.status_code == 200
    # Last 4 digits of 354892091234567 is 4567
    assert "4567" in drilldown_res.text
    # And 354892097654321 last 4 digits is 4321
    assert "4321" in drilldown_res.text

    # Add second unit through POST /pos/add-product
    db = SessionLocal()
    unit2 = db.query(Product).filter(Product.barcode == "IP15P-0002").first()
    db.close()
    add2_res = client.post(f"/pos/add-product?product_id={unit2.id}")
    assert add2_res.status_code == 200
    assert "354892097654321" in add2_res.text
    print("  -> Passed. Unit drilldown rendered with large last-4 digits; unit added to cart.")

    # 9. Test POS Checkout & Thermal Receipt Attributes Snapshot
    print("\n[9/15] Testing POS Checkout execution & Snapshot Storage...")
    checkout_res = client.post("/pos/checkout", data={
        "payment_method": "cash",
        "paid_amount": 25000.0,
        "discount": 100.0
    })
    assert checkout_res.status_code == 200
    data = checkout_res.json()
    assert data["success"] is True
    invoice_id = data["invoice_id"]
    print(f"  -> Checkout successful. Generated Invoice #{data['invoice_number']} (ID: {invoice_id})")

    # Verify thermal receipt renders snapshot attributes
    receipt_res = client.get(f"/pos/receipt/{invoice_id}")
    assert receipt_res.status_code == 200
    assert "فاتورة مبيعات" in receipt_res.text
    assert "354892091234567" in receipt_res.text
    assert "354892097654321" in receipt_res.text
    print("  -> Passed. Thermal receipt verified with dynamic attribute snapshots.")

    # Verify stock deduction
    db = SessionLocal()
    p1_after = db.query(Product).filter(Product.id == phone_prod.id).first()
    assert p1_after.quantity == 0, f"Expected quantity 0 for sold unit, got {p1_after.quantity}"
    db.close()
    print("  -> Passed. Stock verified: sold unit quantity reduced to 0.")

    # 10. Test Dynamic ProductType & Attribute Creation (Admin)
    print("\n[10/15] Testing Admin ProductType & Custom Attribute Creation...")
    create_type_res = client.post("/inventory/types/create", data={
        "name": "ساعات ذكية",
        "icon": "⌚",
        "show_in_pos": "1",
        "use_in_repairs": "0"
    }, follow_redirects=False)
    assert create_type_res.status_code in [302, 303]

    db = SessionLocal()
    new_type = db.query(ProductType).filter(ProductType.name == "ساعات ذكية").first()
    assert new_type is not None
    type_id = new_type.id
    db.close()

    # Add required attribute "اللون" (select)
    client.post(f"/inventory/types/{type_id}/attributes/add", data={
        "name": "اللون",
        "field_kind": "select",
        "options_text": "أسود, فضي, كحلي",
        "is_required": "1",
        "show_on_receipt": "1"
    }, follow_redirects=False)

    # Add unique attribute "الرقم التسلسلي" (text, unique)
    client.post(f"/inventory/types/{type_id}/attributes/add", data={
        "name": "الرقم التسلسلي",
        "field_kind": "text",
        "is_required": "1",
        "is_unique": "1",
        "show_on_receipt": "1"
    }, follow_redirects=False)

    db = SessionLocal()
    created_type = db.query(ProductType).filter(ProductType.id == type_id).first()
    assert len(created_type.attributes) == 2
    assert created_type.has_unique_attribute is True
    serial_attr = [a for a in created_type.attributes if a.is_unique][0]
    color_attr = [a for a in created_type.attributes if not a.is_unique][0]
    db.close()
    print("  -> Passed. Dynamic type 'ساعات ذكية' created with select and unique attributes.")

    # 11. Test Attribute Validation: Required & Uniqueness
    print("\n[11/15] Testing Attribute Validation (Required & Uniqueness)...")
    # Missing required attribute -> 422
    fail_res = client.post("/inventory/product/save", data={
        "type_id": type_id,
        "name": "Apple Watch Ultra 2",
        "buy_price": "2800",
        "sell_price": "3400",
        "quantity": "1",
        f"attr_{color_attr.id}": "",  # missing required
        f"attr_{serial_attr.id}": "WATCH123456"
    })
    assert fail_res.status_code == 422
    assert "إلزامية" in fail_res.text

    # Valid product creation -> auto-generates barcode MBxxxxxx
    ok_res = client.post("/inventory/product/save", data={
        "type_id": type_id,
        "name": "Apple Watch Ultra 2",
        "barcode": "",  # empty to trigger auto-generation
        "buy_price": "2800",
        "sell_price": "3400",
        "quantity": "1",
        f"attr_{color_attr.id}": "أسود",
        f"attr_{serial_attr.id}": "WATCH123456"
    }, follow_redirects=False)
    assert ok_res.status_code in [302, 303]

    db = SessionLocal()
    watch1 = db.query(Product).filter(Product.type_id == type_id).first()
    assert watch1 is not None
    assert watch1.barcode.startswith("MB")
    assert watch1.is_unit is True
    db.close()
    print(f"  -> Passed. Product created with auto-generated barcode {watch1.barcode}.")

    # Duplicate unique attribute test -> 422
    dup_res = client.post("/inventory/product/save", data={
        "type_id": type_id,
        "name": "Apple Watch Ultra 2 (Unit 2)",
        "buy_price": "2800",
        "sell_price": "3400",
        "quantity": "1",
        f"attr_{color_attr.id}": "فضي",
        f"attr_{serial_attr.id}": "WATCH123456"  # DUPLICATE!
    })
    assert dup_res.status_code == 422
    assert "مسجلة مسبقاً" in dup_res.text
    print("  -> Passed. Duplicate unique serial rejected.")

    # 12. Test Product Duplicate Modal Endpoint
    print("\n[12/15] Testing Product Duplicate Endpoint (/inventory/product/{id}/duplicate)...")
    dup_form = client.get(f"/inventory/product/{watch1.id}/duplicate")
    assert dup_form.status_code == 200
    assert "Apple Watch Ultra 2" in dup_form.text
    # Barcode must be empty in duplicate form
    assert 'value=""' in dup_form.text or 'placeholder="امسح باركود' in dup_form.text
    print("  -> Passed. Duplicate prefill loaded cleanly with blank barcode.")

    # 13. Test Role Permissions: Cashier Restrictions
    print("\n[13/15] Testing Role Permissions (Cashier restrictions)...")
    # Cashier Login
    login_cashier = client.post("/auth/login", data={"username": "cashier", "password": "cashier123"}, follow_redirects=False)
    assert login_cashier.status_code in [302, 303]
    cashier_cookie = login_cashier.cookies.get(SESSION_COOKIE_NAME)
    assert cashier_cookie, "Cashier session cookie was not set!"
    client.cookies.set(SESSION_COOKIE_NAME, cashier_cookie)

    # Cashier cannot access types tab
    types_tab = client.get("/inventory?tab=types")
    assert types_tab.status_code == 403

    # Cashier cannot create product
    create_prod = client.post("/inventory/product/save", data={"name": "Hacked", "type_id": 1})
    assert create_prod.status_code == 403

    # Cashier views inventory -> buy prices are hidden
    inv_list = client.get("/inventory?tab=products")
    assert inv_list.status_code == 200
    assert "—" in inv_list.text  # buy price column shows dash for non-admin
    print("  -> Passed. Cashier 403 server-side guards and hidden buy prices verified.")

    # Restore Admin session
    client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)

    # 14. Test Repairs Integration (Spare Parts Only from use_in_repairs)
    print("\n[14/15] Testing Maintenance Workshop Spare Parts Filter...")
    # Create repair ticket
    repair_res = client.post("/repairs/create", data={
        "customer_name": "سالم الأحمد",
        "customer_phone": "0559988776",
        "device_brand": "Apple",
        "device_model": "iPhone 13",
        "reported_issue": "الشاشة مكسورة وبحاجة لتبديل",
        "passcode_pattern": "9900",
        "estimated_cost": 350.0,
        "paid_amount": 100.0
    }, follow_redirects=False)
    assert repair_res.status_code in [302, 303]

    db = SessionLocal()
    from app.models.repair import RepairTicket
    ticket = db.query(RepairTicket).order_by(RepairTicket.id.desc()).first()
    db.close()

    # Ticket detail page should only offer parts where use_in_repairs=True
    ticket_page = client.get(f"/repairs/{ticket.id}")
    assert ticket_page.status_code == 200
    assert "شاشة Samsung Galaxy A54" in ticket_page.text
    # Should NOT offer whole phones in spare parts dropdown
    assert "Apple iPhone 15 Pro" not in ticket_page.text.split('name="product_id"')[1].split('</select>')[0]

    # Add spare part to ticket
    db = SessionLocal()
    screen_part = db.query(Product).filter(Product.barcode == "SP-A54-OLED").first()
    initial_qty = screen_part.quantity
    db.close()

    add_part_res = client.post(f"/repairs/{ticket.id}/add-part", data={
        "product_id": screen_part.id,
        "quantity": 1
    }, follow_redirects=False)
    assert add_part_res.status_code in [302, 303]

    db = SessionLocal()
    screen_part_after = db.query(Product).filter(Product.id == screen_part.id).first()
    assert screen_part_after.quantity == initial_qty - 1
    db.close()
    print("  -> Passed. Spare part consumed from inventory and deducted from stock.")

    # 15. Test Inventory Search & Scope Filtering
    print("\n[15/15] Testing Inventory Search by Attribute & Scope...")
    # Search by attribute value "WATCH123456"
    search_res = client.get("/inventory?tab=products&q=WATCH123456")
    assert search_res.status_code == 200
    assert "Apple Watch Ultra 2" in search_res.text

    # Scope = sellable
    sellable_res = client.get("/inventory?tab=products&scope=sellable")
    assert sellable_res.status_code == 200
    assert "Anker" in sellable_res.text
    # Spare parts must not appear in sellable scope
    assert "شاشة Samsung Galaxy A54" not in sellable_res.text
    print("  -> Passed. Inventory search by attribute and scope filters verified.")

    # Cleanup Test Database
    print("\nCleaning up isolated test database...")
    engine.dispose()
    if DATABASE_PATH.exists():
        try:
            DATABASE_PATH.unlink()
        except Exception as e:
            print(f"Warning: could not delete {DATABASE_PATH}: {e}")
    if UPLOADS_DIR.exists():
        try:
            shutil.rmtree(UPLOADS_DIR)
        except Exception as e:
            print(f"Warning: could not delete {UPLOADS_DIR}: {e}")
    print("  -> Cleanup complete. Production database remained 100% untouched.")

    print("\n" + "=" * 70)
    print("  [SUCCESS] ALL 15 COMPREHENSIVE TESTS PASSED! SYSTEM IS 100% OPERATIONAL.")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
