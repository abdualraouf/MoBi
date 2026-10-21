import os
import sys
import time
import socket
import threading
import urllib.request
import webbrowser
from app.config import APP_TITLE, DATABASE_PATH, VERSION
from app.main import app

BANNER = r"""
  __  __       ____  _ 
 |  \/  | ___ | __ )(_)
 | |\/| |/ _ \|  _ \| |
 | |  | | (_) | |_) | |
 |_|  |_|\___/|____/|_|  v""" + VERSION + r""" (Offline 100%)
============================================================
  MoBi - Phone Shop Management & POS System
============================================================
"""

def minimize_console():
    """Minimize the console window to the taskbar on Windows."""
    try:
        if sys.platform == "win32":
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                # SW_SHOWMINNOACTIVE = 7 (minimize without stealing focus from desktop window)
                ctypes.windll.user32.ShowWindow(hwnd, 7)
    except Exception:
        pass

def get_free_port() -> int:
    """Find an available ephemeral port to prevent port conflicts (WinError 10048)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def start_uvicorn(port: int):
    """Run Uvicorn ASGI server with verbose access logs for debugging."""
    import uvicorn
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)
    server.run()

def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Wait until FastAPI is responsive on the chosen port."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/auth/login", timeout=1) as resp:
                if resp.status in (200, 303):
                    return True
        except Exception:
            time.sleep(0.15)
    return False

def main():
    print(BANNER)

    browser_mode = "--browser" in sys.argv

    port = get_free_port()
    print(f"[*] Local Port     : {port}")
    print(f"[*] Database Path  : {DATABASE_PATH}")
    print("[*] Starting ASGI Server with verbose access logs...")

    # Start Uvicorn in background daemon thread
    server_thread = threading.Thread(target=start_uvicorn, args=(port,), daemon=True)
    server_thread.start()

    # Ensure server is running and database is seeded
    if not wait_for_server(port):
        print("[!] Error: Local server failed to start within timeout.")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    print(f"[OK] MoBi server active at : {url}")
    print("[*] Minimizing console to taskbar. Real-time logs will stream below...\n")

    if not browser_mode:
        try:
            import webview
            import webview.localization as loc

            # Localize exit confirmation dialog into Arabic
            loc.original_localization['global.quitConfirmation'] = 'هل أنت متأكد من رغبتك في إغلاق نظام MoBi والخروج؟'
            loc.original_localization['global.ok'] = 'موافق'
            loc.original_localization['global.quit'] = 'إغلاق النظام'
            loc.original_localization['global.cancel'] = 'إلغاء'

            # Auto-minimize the console window to the taskbar
            minimize_console()

            window = webview.create_window(
                title=f"{APP_TITLE} (Offline 100%)",
                url=url,
                width=1280,
                height=820,
                min_size=(1024, 700),
                confirm_close=True,
                text_select=True,
            )
            webview.start(debug=False)
            print("\n[OK] MoBi window closed. Application terminated cleanly.")
            sys.exit(0)
        except Exception as e:
            print(f"[!] Could not launch WebView2 desktop window: {e}")
            print("[*] Falling back to default web browser...")

    # Fallback mode (browser)
    minimize_console()
    print(f"[*] Opening browser at: {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[OK] MoBi server terminated.")

if __name__ == "__main__":
    main()
