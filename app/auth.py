"""Authentication module for Cactus Flasher."""
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from .config import settings, get_credentials, save_credentials

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def authenticate_user(username: str, password: str) -> Optional[str]:
    """Authenticate a user and return their username if valid."""
    credentials = get_credentials()
    users = credentials.get("users", {})

    if username not in users:
        return None

    user_data = users[username]
    if not verify_password(password, user_data.get("password_hash", "")):
        return None

    return username


def create_user(username: str, password: str) -> bool:
    """Create a new user with hashed password."""
    credentials = get_credentials()
    if "users" not in credentials:
        credentials["users"] = {}

    if username in credentials["users"]:
        return False

    credentials["users"][username] = {
        "password_hash": hash_password(password),
        "created_at": datetime.utcnow().isoformat(),
    }
    save_credentials(credentials)
    return True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Dependency to get the current authenticated user."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username


def init_default_admin():
    """Initialize default admin user if no users exist."""
    credentials = get_credentials()
    if not credentials.get("users"):
        create_user("admin", "cactus123")
        print("Created default admin user (username: admin, password: cactus123)")
