import sys
import time
import threading
import webbrowser
import uvicorn
from app.config import HOST, PORT, APP_TITLE
from app.database_init import init_db

def open_browser():
    """Wait briefly for the server to start, then open the default browser."""
    time.sleep(1.2)
    url = f"http://{HOST}:{PORT}"
    print(f"\n[MoBi] جاري فتح واجهة النظام في المتصفح: {url}\n")
    webbrowser.open(url)

def main():
    print("=" * 60)
    print(f"       {APP_TITLE} (Offline 100%)")
    print("=" * 60)
    
    # 1. Initialize Database & Seed default records if needed
    print("[1/2] فحص وتهيئة قاعدة البيانات المحلية...")
    init_db()

    # 2. Schedule browser auto-open
    print(f"[2/2] تشغيل السيرفر المحلي على: http://{HOST}:{PORT}")
    threading.Thread(target=open_browser, daemon=True).start()

    # 3. Start Uvicorn Server
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="info", access_log=False)

if __name__ == "__main__":
    main()
