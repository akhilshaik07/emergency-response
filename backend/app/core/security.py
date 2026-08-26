"""Authentication, password hashing, and JWT utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, ExpiredSignatureError, JWTError
from passlib.context import CryptContext
from app.core.config import settings

# Private password hashing context (never exposed directly outside this module)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenExpiredError(Exception):
    """Raised when a JWT has expired."""
    pass


class TokenInvalidError(Exception):
    """Raised when a JWT has an invalid signature, malformed structure, or corrupt claims."""
    pass


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a short-lived JWT access token containing subject (user_id) and role.

    ARCHITECTURAL NOTE ON EMBEDDED ROLE CLAIM:
    Embedding `role` directly in the access token allows role-based route guards to verify
    authorization without an extra database query on every single HTTP request.
    ACCEPTED TRADEOFF: If a user's role is updated in the database, the change will NOT take
    effect for that active session until their access token expires and is refreshed/re-issued.
    """
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "role": str(role),
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a long-lived JWT refresh token containing only subject (user_id).

    ARCHITECTURAL NOTE:
    Refresh tokens deliberately carry minimal claims (no `role`). When exchanging a refresh
    token for a new access token, the user's current role is re-resolved from the database,
    ensuring role updates take effect at latest on the next token refresh cycle.
    """
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the signature is invalid or the token is malformed.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except ExpiredSignatureError as e:
        raise TokenExpiredError("Token has expired") from e
    except JWTError as e:
        raise TokenInvalidError("Token signature or structure is invalid") from e
