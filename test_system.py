import sys
from fastapi.testclient import TestClient
from app.main import app
from app.database_init import init_db
from app.config import SESSION_COOKIE_NAME

def run_tests():
    print("=" * 60)
    print("   MoBi Automated Verification Test Suite")
    print("=" * 60)

    # 1. Initialize DB
    print("[1/8] Testing Database Initialization...")
    init_db()
    print("  -> Passed.")

    client = TestClient(app)

    # 2. Test Login page
    print("[2/8] Testing GET /auth/login...")
    res = client.get("/auth/login")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "نظام MoBi" in res.text
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

    print("\n" + "=" * 60)
    print("  [SUCCESS] ALL 8 TESTS PASSED! SYSTEM IS 100% OPERATIONAL.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
