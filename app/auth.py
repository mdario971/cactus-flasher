"""Authentication module for Cactus Flasher."""
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from .config import settings, get_credentials, save_credentials

security = HTTPBearer()


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength.

    Requirements: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char.
    Returns (is_valid, error_message).
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        return False, "Password must contain at least one special character (!@#$%^&*...)"
    return True, ""


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


def create_user(username: str, password: str, skip_validation: bool = False) -> Tuple[bool, str]:
    """Create a new user with hashed password.

    Returns (success, error_message). Password validation is enforced unless skip_validation=True.
    """
    if not skip_validation:
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return False, error_msg

    credentials = get_credentials()
    if "users" not in credentials:
        credentials["users"] = {}

    if username in credentials["users"]:
        return False, "Username already exists"

    credentials["users"][username] = {
        "password_hash": hash_password(password),
        "created_at": datetime.utcnow().isoformat(),
    }
    save_credentials(credentials)
    return True, ""


def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """Change a user's password. Returns (success, error_message)."""
    credentials = get_credentials()
    users = credentials.get("users", {})

    if username not in users:
        return False, "User not found"

    if not verify_password(old_password, users[username].get("password_hash", "")):
        return False, "Current password is incorrect"

    is_valid, error_msg = validate_password(new_password)
    if not is_valid:
        return False, error_msg

    credentials["users"][username]["password_hash"] = hash_password(new_password)
    credentials["users"][username]["password_changed_at"] = datetime.utcnow().isoformat()
    save_credentials(credentials)
    return True, ""


def delete_user(username: str, current_user: str) -> Tuple[bool, str]:
    """Delete a user. Cannot delete self or the last remaining user."""
    if username == current_user:
        return False, "Cannot delete your own account"

    credentials = get_credentials()
    users = credentials.get("users", {})

    if username not in users:
        return False, "User not found"

    if len(users) <= 1:
        return False, "Cannot delete the last remaining user"

    del credentials["users"][username]
    save_credentials(credentials)
    return True, ""


def list_users() -> List[dict]:
    """Return list of users with metadata (no password hashes)."""
    credentials = get_credentials()
    users = credentials.get("users", {})
    result = []
    for uname, data in users.items():
        result.append({
            "username": uname,
            "created_at": data.get("created_at", ""),
            "password_changed_at": data.get("password_changed_at"),
        })
    return result


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
        create_user("admin", "cactus123", skip_validation=True)
        print("Created default admin user (username: admin, password: cactus123)")
        print("WARNING: Change the default password immediately via Settings > User Management!")
