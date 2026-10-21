import os
import sys
import time
import socket
import threading
import urllib.request
import webbrowser
from app.config import APP_NAME, APP_TITLE, DATABASE_PATH, VERSION, STATIC_DIR
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

def set_windows_app_user_model_id():
    """Ensure Windows taskbar treats MoBi as a distinct application rather than generic python.exe."""
    if sys.platform == "win32":
        try:
            import ctypes
            # Explicit AppUserModelID forces the Windows taskbar to decouple this window
            # from python.exe and display the application's own custom icon on the taskbar.
            app_id = "MoBi.PhoneShop.POS.DesktopApp.v1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

def apply_native_icons(icon_path: str, shop_name: str = ""):
    """
    Apply native Windows icons via Win32 API to all windows belonging to this process
    (both WebView2 form and Console Window). Sends WM_SETICON (big and small) and
    updates window class icon to ensure the taskbar and titlebar display the custom icon.
    """
    if sys.platform != "win32" or not os.path.isfile(icon_path):
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    GCLP_HICON = -14
    GCLP_HICONSM = -34

    try:
        # Load big (32x32/48x48) and small (16x16) icon handles from ICO file
        hicon_big = user32.LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        hicon_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = hicon_small
        if not hicon_small:
            hicon_small = hicon_big

        if not hicon_big:
            return

        # 1. Update the console window if present
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            user32.SendMessageW(console_hwnd, WM_SETICON, ICON_BIG, hicon_big)
            user32.SendMessageW(console_hwnd, WM_SETICON, ICON_SMALL, hicon_small)

        # 2. Watch for the WebView window to appear, and apply icons
        def inject_icons():
            my_pid = os.getpid()
            for _ in range(40):  # poll up to 8 seconds
                time.sleep(0.2)
                found = []

                def enum_proc(hwnd, _):
                    if user32.IsWindowVisible(hwnd):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value == my_pid:
                            found.append(hwnd)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

                for hwnd in found:
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                    try:
                        user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon_big)
                        user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
                    except AttributeError:
                        user32.SetClassLongW(hwnd, GCLP_HICON, hicon_big)
                        user32.SetClassLongW(hwnd, GCLP_HICONSM, hicon_small)

                if found:
                    break

        threading.Thread(target=inject_icons, daemon=True).start()
    except Exception as e:
        print(f"[*] Icon injection error: {e}")

def minimize_console(icon_path: str = None):
    """Minimize the console window to the taskbar on Windows and set its icon."""
    try:
        if sys.platform == "win32":
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                if icon_path:
                    apply_native_icons(icon_path)
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

def get_shop_branding() -> tuple[str, str]:
    """Retrieve shop name and the active window icon from settings."""
    shop_name = APP_NAME
    default_icon = str(STATIC_DIR / "favicon.ico")
    icon_path = default_icon
    try:
        from app.database import SessionLocal
        from app.models.settings import ShopSettings
        with SessionLocal() as db:
            settings = db.query(ShopSettings).first()
            if settings:
                if settings.shop_name:
                    shop_name = settings.shop_name
                if settings.logo_path:
                    custom_ico = STATIC_DIR / "uploads" / "shop_icon.ico"
                    if custom_ico.exists():
                        icon_path = str(custom_ico)
    except Exception:
        pass
    return shop_name, icon_path

def main():
    print(BANNER)

    # Initialize Windows AppUserModelID early so Windows decouples from python.exe
    set_windows_app_user_model_id()

    shop_name, icon_path = get_shop_branding()

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

            # Auto-minimize the console window to the taskbar and apply custom icon
            minimize_console(icon_path)

            print(f"[*] Window Title   : {shop_name}")
            print(f"[*] Window Icon    : {icon_path}")

            window = webview.create_window(
                title=shop_name,
                url=url,
                width=1280,
                height=820,
                min_size=(1024, 700),
                confirm_close=True,
                text_select=True,
            )

            # Apply native taskbar icons when window is shown
            window.events.shown += lambda: apply_native_icons(icon_path, shop_name)
            apply_native_icons(icon_path, shop_name)

            webview.start(icon=icon_path, debug=False)
            print("\n[OK] MoBi window closed. Application terminated cleanly.")
            sys.exit(0)
        except Exception as e:
            print(f"[!] Could not launch WebView2 desktop window: {e}")
            print("[*] Falling back to default web browser...")

    # Fallback mode (browser)
    minimize_console(icon_path)
    print(f"[*] Opening browser at: {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[OK] MoBi server terminated.")

if __name__ == "__main__":
    main()
