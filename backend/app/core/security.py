from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from passlib.context import CryptContext
from app.core.config import settings
from loguru import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: str | Any, expires_delta: timedelta | None = None, extra_payload: dict | None = None) -> str:  # timedelta 不接受 None
    if not settings.SECRET_KEY:  # C-03 SECRET_KEY空值校验，防止用空密钥签发可伪造令牌
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

def create_refresh_token(subject: str | Any) -> str:
    if not settings.SECRET_KEY:  # C-03 SECRET_KEY空值校验，防止用空密钥签发可伪造令牌
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


def verify_token(token: str, audience: str = "pygbsentry:access") -> dict:
    """Verify and decode a JWT token with full validation.

    Args:
        token: The JWT token string
        audience: Expected audience (pygbsentry:access or pygbsentry:refresh)

    Returns:
        The decoded token payload

    Raises:
        jwt.InvalidTokenError: If the token is invalid, expired, or audience doesn't match
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=audience,
        issuer="PyGBSentry",
    )
    return payload


async def verify_token_async(token: str, audience: str = "pygbsentry:access") -> dict:
    payload = verify_token(token, audience)
    user_id = payload.get("sub")
    if user_id:
        from app.core.redis import redis_client
        if redis_client:
            try:
                revoked_at = await redis_client.get(f"user_token_revoked:{user_id}")
                if revoked_at:
                    issued_at = payload.get("iat")
                    if issued_at is None or float(issued_at) < float(revoked_at):
                        raise jwt.InvalidTokenError("Token has been revoked")
            except jwt.InvalidTokenError:
                raise
            except Exception as e:
                # P1-1: fail-closed 策略 — 生产环境 Redis 故障时拒绝请求，防止已吊销 token 被放行
                # dev/test 环境降级放行（仅告警），避免本地无 Redis 时无法登录
                from app.core.config import settings
                _env = (getattr(settings, "APP_ENV", "dev") or "dev").lower()
                logger.warning(f"Redis token revocation check failed for user {user_id}: {e}")
                if _env in {"prod", "production"}:
                    raise jwt.InvalidTokenError("Token revocation check unavailable (Redis down)")
                # 非生产环境降级放行
    return payload
