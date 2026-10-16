import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import SECRET_KEY, SESSION_COOKIE_NAME
from app.models.user import User

serializer = URLSafeTimedSerializer(SECRET_KEY)

def hash_password(plain_password: str) -> str:
    """Hash a plain text password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_session_token(user: User) -> str:
    """Create a signed, secure session token containing user id and role."""
    data = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name
    }
    return serializer.dumps(data, salt="mobi-session-salt")

def verify_session_token(token: str, max_age: int = 60 * 60 * 24 * 7) -> dict | None:
    """
    Verify and unpack a session token.
    Valid for 7 days by default. Returns payload dict or None.
    """
    if not token:
        return None
    try:
        payload = serializer.loads(token, salt="mobi-session-salt", max_age=max_age)
        return payload
    except (BadSignature, SignatureExpired):
        return None
