from fastapi.templating import Jinja2Templates
from app.config import TEMPLATES_DIR
from app.database import SessionLocal
from app.models.settings import ShopSettings

# Unified Jinja2Templates instance for entire MoBi application
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def get_shop_settings():
    """Retrieve the current shop settings from the database for templates."""
    db = SessionLocal()
    try:
        return db.query(ShopSettings).first()
    finally:
        db.close()

# Register globally in Jinja environment so all templates can access current shop branding
templates.env.globals["get_shop_settings"] = get_shop_settings
