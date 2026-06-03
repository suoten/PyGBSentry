from datetime import datetime, timedelta, timezone
from typing import Union, Any
import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: timedelta | None = None, extra_payload: dict | None = None) -> str:  # FIXED: timedelta 不接受 None
    if not settings.SECRET_KEY:  # FIXED-P0: C-03 SECRET_KEY空值校验，防止用空密钥签发可伪造令牌
        raise ValueError("SECRET_KEY is not configured; cannot create access token")
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iss": "PyGBSentry",
        "aud": "pygbsentry:access",
    }
    if extra_payload:
        to_encode.update(extra_payload)
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any]) -> str:
    if not settings.SECRET_KEY:  # FIXED-P0: C-03 SECRET_KEY空值校验，防止用空密钥签发可伪造令牌
        raise ValueError("SECRET_KEY is not configured; cannot create refresh token")
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iss": "PyGBSentry",
        "aud": "pygbsentry:refresh",
        "type": "refresh",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
