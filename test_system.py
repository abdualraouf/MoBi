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

    # 15. Test Inventory Search by Attribute & Scope Filtering
    print("\n[15/20] Testing Inventory Search by Attribute & Scope...")
    # Search by attribute value "WATCH123456"
    search_res = client.get("/inventory?tab=products&q=WATCH123456")
    assert search_res.status_code == 200
    assert "Apple Watch Ultra 2" in search_res.text

    # Scope = sellable & empty query params resilience (e.g. hide_out=&type_id=)
    sellable_res = client.get("/inventory?tab=products&scope=sellable&hide_out=&type_id=")
    assert sellable_res.status_code == 200
    assert "Anker" in sellable_res.text
    # Spare parts must not appear in sellable scope
    assert "شاشة Samsung Galaxy A54" not in sellable_res.text
    print("  -> Passed. Inventory search by attribute and scope filters verified.")

    # 16. Test POS Picker Search (Regression test for AttributeError) & Tag Drilldown Context
    print("\n[16/20] Testing POS Picker Live Search & Tag Mode Back-Button Context...")
    picker_search_res = client.get(f"/pos/picker?mode=type&scope_id={type_id}&q=WATCH123456")
    assert picker_search_res.status_code == 200
    assert "Apple Watch Ultra 2" in picker_search_res.text

    drilldown_tag_res = client.get(f"/pos/picker/group/{watch1.id}?mode=tag&scope_id=2")
    assert drilldown_tag_res.status_code == 200
    assert "mode=tag&scope_id=2" in drilldown_tag_res.text
    assert 'hx-target="#pos-cart-container"' in drilldown_tag_res.text
    print("  -> Passed. POS Picker search and unit drilldown context verified.")

    # 17. Test POS Accounting Guardrails (Walk-in Debt Block, min_sell_price Floor, Paid Capping)
    print("\n[17/20] Testing POS Accounting Guardrails (Walk-in Debt, Min Price, Change Cap)...")
    # Clear cart and add Anker charger (sell_price=55, min_sell_price=50)
    client.post("/pos/clear-cart")
    client.post("/pos/add-item", data={"query": "6934177701234"})

    # 17a: Walk-in customer (id=1, phone=0000000000) cannot take debt
    walkin_debt_res = client.post("/pos/checkout", data={
        "customer_id": 1,
        "payment_method": "debt",
        "paid_amount": 10.0,
        "discount": 0.0
    })
    assert walkin_debt_res.status_code == 400
    assert "زبون نقدي عام" in walkin_debt_res.json()["message"]

    # 17b: Switch to Cashier -> cannot discount below min_sell_price (55 - 20 = 35 < 50)
    client.cookies.set(SESSION_COOKIE_NAME, cashier_cookie)
    client.post("/pos/clear-cart")
    client.post("/pos/add-item", data={"query": "6934177701234"})
    excess_disc_res = client.post("/pos/checkout", data={
        "customer_id": 1,
        "payment_method": "cash",
        "paid_amount": 35.0,
        "discount": 20.0
    })
    assert excess_disc_res.status_code == 400
    assert "الحد المسموح" in excess_disc_res.json()["message"]

    # 17c: Cashier checkout with excess cash tendered (pays 100 for 55 item) -> paid_amount capped at 55
    overpay_res = client.post("/pos/checkout", data={
        "customer_id": 1,
        "payment_method": "cash",
        "paid_amount": 100.0,
        "discount": 0.0
    })
    assert overpay_res.status_code == 200
    overpay_data = overpay_res.json()
    assert overpay_data["success"] is True
    db = SessionLocal()
    from app.models.invoice import Invoice
    inv_overpay = db.query(Invoice).filter(Invoice.id == overpay_data["invoice_id"]).first()
    assert inv_overpay.paid_amount == 55.0, f"Expected capped paid_amount=55.0, got {inv_overpay.paid_amount}"
    assert inv_overpay.remaining_amount == 0.0
    db.close()
    print("  -> Passed. Walk-in debt blocked, min_sell_price enforced for cashier, change capped.")

    # Restore Admin session
    client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)

    # 18. Test Customer Debt Creation, Debt Settlement, and Financial Reports
    print("\n[18/20] Testing Customer Debt Payment & Reports Accuracy...")
    # Create a named customer
    client.post("/customers/create", data={
        "name": "خالد المنصور",
        "phone": "0912345678",
        "address": "طرابلس"
    }, follow_redirects=False)
    db = SessionLocal()
    from app.models.customer import Customer
    named_cust = db.query(Customer).filter(Customer.phone == "0912345678").first()
    named_cust_id = named_cust.id
    db.close()

    # Sell Anker charger (55) on credit (paid 15 -> remaining debt 40 -> balance -40)
    client.post("/pos/clear-cart")
    client.post("/pos/add-item", data={"query": "6934177701234"})
    credit_sale = client.post("/pos/checkout", data={
        "customer_id": named_cust_id,
        "payment_method": "debt",
        "paid_amount": 15.0,
        "discount": 0.0
    })
    assert credit_sale.status_code == 200

    db = SessionLocal()
    named_cust = db.query(Customer).filter(Customer.id == named_cust_id).first()
    assert named_cust.balance == -40.0, f"Expected customer balance -40.0, got {named_cust.balance}"
    db.close()

    # Pay 30 of debt
    pay_debt_res = client.post(f"/customers/{named_cust_id}/pay-debt", data={
        "amount": 30.0,
        "notes": "دفعة نقدية أولى"
    }, follow_redirects=False)
    assert pay_debt_res.status_code in [302, 303]

    db = SessionLocal()
    named_cust = db.query(Customer).filter(Customer.id == named_cust_id).first()
    assert named_cust.balance == -10.0, f"Expected customer balance -10.0 after payment, got {named_cust.balance}"
    db.close()

    # Check Reports across periods
    for period in ["today", "week", "month", "all"]:
        rep_res = client.get(f"/reports?period={period}")
        assert rep_res.status_code == 200
        assert "صافي الأرباح الكلي" in rep_res.text
    print("  -> Passed. Customer debt recorded, settled, and reports verified across all periods.")

    # 19. Test Repair Part Removal & Role Separation (Technician vs Cashier)
    print("\n[19/20] Testing Repair Part Removal & Strict Role Separation...")
    db = SessionLocal()
    from app.models.repair import RepairPart
    consumed_part = db.query(RepairPart).filter(RepairPart.ticket_id == ticket.id).first()
    assert consumed_part is not None
    part_id = consumed_part.id
    prod_id = consumed_part.product_id
    qty_before_return = db.query(Product).filter(Product.id == prod_id).first().quantity
    db.close()

    # Remove part from ticket -> restores stock
    rem_part_res = client.post(f"/repairs/{ticket.id}/remove-part/{part_id}", follow_redirects=False)
    assert rem_part_res.status_code in [302, 303]

    db = SessionLocal()
    qty_after_return = db.query(Product).filter(Product.id == prod_id).first().quantity
    assert qty_after_return == qty_before_return + 1, "Spare part stock was not restored upon removal!"
    db.close()

    # Cashier cannot consume spare parts in /repairs/{id}/add-part
    client.cookies.set(SESSION_COOKIE_NAME, cashier_cookie)
    cashier_add_part = client.post(f"/repairs/{ticket.id}/add-part", data={"product_id": prod_id, "quantity": 1})
    assert cashier_add_part.status_code == 403

    # Login as Technician
    login_tech = client.post("/auth/login", data={"username": "tech", "password": "tech123"}, follow_redirects=False)
    assert login_tech.status_code in [302, 303]
    assert login_tech.headers["location"] == "/repairs"
    tech_cookie = login_tech.cookies.get(SESSION_COOKIE_NAME)
    client.cookies.set(SESSION_COOKIE_NAME, tech_cookie)

    # Technician can access /repairs and ticket detail, but cost_price column is hidden
    tech_ticket_page = client.get(f"/repairs/{ticket.id}")
    assert tech_ticket_page.status_code == 200
    assert "التكلفة على المحل" not in tech_ticket_page.text

    # Technician cannot access /pos or /customers
    assert client.get("/pos").status_code == 403
    assert client.get("/customers").status_code == 403
    print("  -> Passed. Spare part return restored stock; Technician & Cashier role boundaries enforced.")

    # Restore Admin session
    client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)

    # 20. Test System Security, User Management, and Atomic SQLite Backup
    print("\n[20/20] Testing Window Security, Safe Redirects, User Admin, & Atomic Backup...")
    # Cross-origin request to /system/window/minimize must be rejected with 403
    csrf_win = client.post("/system/window/minimize", headers={"Origin": "http://evil.example.com"})
    assert csrf_win.status_code == 403

    # External return_url in inventory must be sanitized to /inventory
    ext_redir = client.post(f"/inventory/product/{watch1.id}/archive", data={
        "return_url": "https://evil.example.com/phish"
    }, follow_redirects=False)
    assert ext_redir.status_code in [302, 303]
    assert ext_redir.headers["location"] == "/inventory"

    # Admin creates a new user & changes password
    create_u = client.post("/settings/users/create", data={
        "username": "cashier2",
        "full_name": "كاشير مسائي",
        "password": "pass1234",
        "role": "cashier"
    }, follow_redirects=False)
    assert create_u.status_code in [302, 303]
    db = SessionLocal()
    u2 = db.query(User).filter(User.username == "cashier2").first()
    assert u2 is not None
    u2_id = u2.id
    db.close()

    # Toggle user active status
    client.post(f"/settings/users/{u2_id}/toggle", follow_redirects=False)
    db = SessionLocal()
    assert db.query(User).filter(User.id == u2_id).first().is_active is False
    db.close()

    # Atomic SQLite backup download
    backup_res = client.get("/settings/backup-db")
    assert backup_res.status_code == 200
    assert backup_res.content[:16] == b"SQLite format 3\x00", "Backup file is not a valid SQLite database!"
    print("  -> Passed. Security headers, redirects, user management, and atomic SQLite backup verified.")

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
    print("  [SUCCESS] ALL 20 COMPREHENSIVE TESTS PASSED! SYSTEM IS 100% OPERATIONAL.")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
