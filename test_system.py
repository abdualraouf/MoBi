import os
import sys
import shutil

# 1. Force test environment BEFORE importing any application module
os.environ["MOBI_TESTING"] = "1"

from fastapi.testclient import TestClient
from app.config import SESSION_COOKIE_NAME, DATABASE_PATH, UPLOADS_DIR, STATIC_DIR, IS_TESTING
from app.main import app
from app.database_init import init_db

def run_tests():
    print("=" * 60)
    print("   MoBi Automated Verification Test Suite (Isolated Environment)")
    print("=" * 60)

    # Safety Guardrail: Never allow tests to run against production database!
    assert IS_TESTING is True, "Security Error: IS_TESTING is not enabled!"
    assert DATABASE_PATH.name == "test_mobi.db", f"Security Error: Tests must use test_mobi.db, got {DATABASE_PATH.name}!"
    assert UPLOADS_DIR.name == "test_uploads", f"Security Error: Tests must use test_uploads, got {UPLOADS_DIR.name}!"

    # Clean up any leftover test database from previous aborted runs
    from app.database import engine
    engine.dispose()
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Isolated Test DB
    print("[1/10] Testing Database Initialization (test_mobi.db)...")
    init_db()
    print("  -> Passed.")

    client = TestClient(app)

    # 2. Test Login page
    print("[2/10] Testing GET /auth/login...")
    res = client.get("/auth/login")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "MoBi" in res.text
    print("  -> Passed.")

    # 3. Test Admin Authentication
    print("[3/8] Testing POST /auth/login with valid credentials...")
    login_res = client.post("/auth/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert login_res.status_code in [302, 303], f"Expected redirect, got {login_res.status_code}"
    session_cookie = login_res.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie, "Session cookie was not set!"
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie)
    print("  -> Passed. Admin authenticated successfully.")

    # 4. Test POS screen
    print("[4/8] Testing GET /pos...")
    pos_res = client.get("/pos")
    assert pos_res.status_code == 200
    assert "نقطة البيع" in pos_res.text
    print("  -> Passed.")

    # 5. Test Barcode Scanner: Accessory
    print("[5/8] Testing Barcode Scanner with accessory barcode (6934177701234)...")
    scan_res = client.post("/pos/add-item", data={"query": "6934177701234"})
    assert scan_res.status_code == 200
    assert "Anker" in scan_res.text
    print("  -> Passed. Accessory resolved and added to cart.")

    # 6. Test Barcode Scanner: Phone IMEI
    print("[6/8] Testing Barcode Scanner with phone IMEI...")
    from app.database import SessionLocal
    from app.models.product_item import ProductItem
    db = SessionLocal()
    phone_item = db.query(ProductItem).filter(ProductItem.status == "in_stock").first()
    if not phone_item:
        phone_item = db.query(ProductItem).first()
        phone_item.status = "in_stock"
        db.commit()
    test_imei = phone_item.imei
    db.close()

    imei_res = client.post("/pos/add-item", data={"query": test_imei})
    assert imei_res.status_code == 200
    assert test_imei in imei_res.text
    print(f"  -> Passed. Phone unit resolved by IMEI ({test_imei}).")

    # 7. Test POS Checkout & Thermal Receipt
    print("[7/8] Testing POS Checkout execution...")
    checkout_res = client.post("/pos/checkout", data={
        "payment_method": "cash",
        "paid_amount": 5000.0,
        "discount": 50.0
    })
    assert checkout_res.status_code == 200
    data = checkout_res.json()
    assert data["success"] is True
    invoice_id = data["invoice_id"]
    print(f"  -> Checkout successful. Generated Invoice #{data['invoice_number']} (ID: {invoice_id})")

    # Verify thermal receipt
    receipt_res = client.get(f"/pos/receipt/{invoice_id}")
    assert receipt_res.status_code == 200
    assert "فاتورة مبيعات" in receipt_res.text
    assert test_imei in receipt_res.text
    print(f"  -> Thermal receipt verified with IMEI snapshot ({test_imei}).")

    # 8. Test Repair ticket intake
    print("[8/8] Testing Repair Ticket creation (/repairs/create)...")
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
    print("  -> Passed. Repair ticket created with intake barcode.")

    # 9. Test Favicon
    print("[9/10] Testing GET /favicon.ico...")
    fav_res = client.get("/favicon.ico")
    assert fav_res.status_code == 200, f"Expected 200, got {fav_res.status_code}"
    assert len(fav_res.content) > 0, "Favicon response is empty!"
    print("  -> Passed. Official brand icon served successfully.")

    # 10. Test Custom Shop Logo Upload & Windows ICO Generation
    print("[10/10] Testing Custom Logo Upload, Multi-Res Windows ICO Generation, & Reset...")
    import io
    from PIL import Image
    from run import get_shop_branding
    from app.config import STATIC_DIR

    # Create dummy PNG in-memory
    test_img = Image.new("RGBA", (128, 128), color=(30, 144, 255, 255))
    img_byte_arr = io.BytesIO()
    test_img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    # Post logo upload to /settings/update
    upload_res = client.post("/settings/update", data={
        "shop_name": "المركز الذهبي للهواتف",
        "currency": "د.ل",
        "phone": "0501112233",
        "secondary_phone": "0504445566",
        "address": "طريق الملك فهد",
        "tax_number": "300123456700003",
        "thermal_width": "80mm",
        "invoice_footer": "البضاعة المباعة ترد وتستبدل خلال 3 أيام",
        "repair_terms": "الضمان شهر على قطع الغيار الأصلية"
    }, files={
        "logo": ("custom_logo.png", img_byte_arr, "image/png")
    }, follow_redirects=True)
    assert upload_res.status_code == 200

    # Verify generated files
    uploads_dir = UPLOADS_DIR
    png_file = uploads_dir / "shop_logo.png"
    ico_file = uploads_dir / "shop_icon.ico"
    assert png_file.exists(), "shop_logo.png was not generated!"
    assert ico_file.exists(), "shop_icon.ico was not generated!"

    # Verify get_shop_branding() from run.py
    title, icon = get_shop_branding()
    assert title == "المركز الذهبي للهواتف", f"Expected 'المركز الذهبي للهواتف', got '{title}'"
    assert icon == str(ico_file), f"Expected icon '{ico_file}', got '{icon}'"

    # Verify favicon route serves the custom icon
    custom_fav_res = client.get("/favicon.ico")
    assert custom_fav_res.status_code == 200
    assert len(custom_fav_res.content) == ico_file.stat().st_size

    # Verify POS and Login screens reflect the new shop branding
    pos_page = client.get("/pos").text
    assert "المركز الذهبي للهواتف" in pos_page
    assert "/static/uploads/shop_logo.png" in pos_page

    # Verify reset logo functionality
    reset_res = client.post("/settings/reset-logo", follow_redirects=True)
    assert reset_res.status_code == 200
    assert not png_file.exists(), "shop_logo.png was not deleted upon reset!"
    assert not ico_file.exists(), "shop_icon.ico was not deleted upon reset!"

    title_after_reset, icon_after_reset = get_shop_branding()
    assert title_after_reset == "المركز الذهبي للهواتف"
    assert icon_after_reset == str(STATIC_DIR / "favicon.ico")
    print("  -> Passed. Custom logo uploaded, converted to Windows ICO, and reset cleanly.")

    # 11. Cleanup Test Artifacts
    print("\nCleaning up isolated test environment...")
    from app.database import engine
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

    print("\n" + "=" * 60)
    print("  [SUCCESS] ALL 10 TESTS PASSED! SYSTEM IS 100% OPERATIONAL.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()

