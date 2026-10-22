import os
import sys
from pathlib import Path

# Determine base directory whether running as script or bundled executable
if getattr(sys, 'frozen', False):
    # PyInstaller bundle directory (where bundled static/templates are extracted)
    BUNDLE_DIR = Path(sys._MEIPASS)
    # Executable directory (where the .exe lives and where mobi.db should be saved)
    DATA_DIR = Path(sys.executable).parent
else:
    # Development directory
    BUNDLE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BUNDLE_DIR

APP_DIR = BUNDLE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

# Persistent Storage & Test Environment Isolation
IS_TESTING = os.getenv("MOBI_TESTING") == "1"

if IS_TESTING:
    DATABASE_PATH = DATA_DIR / "test_mobi.db"
    UPLOADS_DIR = DATA_DIR / "test_uploads"
else:
    DATABASE_PATH = DATA_DIR / "mobi.db"
    UPLOADS_DIR = DATA_DIR / "uploads"

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Security & Sessions
SECRET_KEY = os.getenv("MOBI_SECRET_KEY", "mobi-secure-offline-secret-key-phone-pos-2026")
SESSION_COOKIE_NAME = "mobi_session"

# Application Metadata
APP_NAME = "MoBi"
APP_TITLE = "MoBi | نظام إدارة محلات الهواتف ونقاط البيع والصيانة"
VERSION = "1.0.0"
HOST = "127.0.0.1"
PORT = 8000
