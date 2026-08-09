from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
import bcrypt
from app.core.config import settings
from loguru import logger

# P0-SEC [2026-07-17]: 移除 passlib（自 2020 年停止维护，且与 bcrypt>=4.1 存在
# __about__ 属性读取报错 bug），改为直接使用 bcrypt 库。
# passlib CryptContext 生成的 bcrypt 哈希格式 ($2b$12$...) 与原生 bcrypt 完全兼容，
# 存量用户密码哈希无需迁移即可通过 bcrypt.checkpw 验证。

ALGORITHM = "HS256"

# bcrypt 计算成本因子（rounds）。passlib 默认 12 轮，保持一致以确保
# 新生成哈希的安全强度与历史 passlib 生成的哈希一致。
_BCRYPT_ROUNDS = 12


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。

    与 passlib CryptContext.verify 行为一致：
    - 明文或哈希为空/None 时返回 False（不抛异常）
    - 哈希格式非法（非 $2b$/$2a$/$2y$）时返回 False（不抛异常）
    - 兼容 passlib 生成的存量哈希（$2b$ 格式）
    """
    if not plain_password or not hashed_password:
        return False
    try:
        # bcrypt.checkpw 要求 bytes 输入；哈希通常是 str（来自数据库）
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError) as e:
        # 非法哈希格式（如长度不足、前缀错误）— bcrypt 抛 ValueError
        logger.debug(f"verify_password: invalid hash format rejected: {e}")
        return False
    except Exception as e:
        # 兜底：其他意外错误不暴露细节，仅记录并拒绝
        logger.warning(f"verify_password: unexpected error during verification: {e}")
        return False


def get_password_hash(password: str) -> str:
    """使用 bcrypt 生成密码哈希（$2b$ 格式，12 轮）。

    返回 str 类型（与 passlib CryptContext.hash 一致），可直接存入数据库的
    hashed_password 列。生成的哈希格式与 passlib 完全兼容。
    """
    if not password:
        raise ValueError("Password must not be empty")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(subject: str | Any, expires_delta: timedelta | None = None, extra_payload: dict | None = None) -> str:  # timedelta 不接受 None
    if not settings.SECRET_KEY:  # C-03 SECRET_KEY空值校验，防止用空密钥签发可伪造令牌
        raise ValueError("SECRET_KEY is not configured; cannot create access token")
    _now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = _now + expires_delta
    else:
        expire = _now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": _now,  # FIX: [2026-07-16 P0-A] 添加 iat 声明，修复 token 吊销机制。
        # verify_token_async 依赖 iat 判断 token 是否在密码修改后签发，
        # 缺失 iat 会导致 user_token_revoked 键存在时所有 token 被误判为已吊销，
        # 用户修改密码后被锁定 2 小时无法登录。
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
    _now = datetime.now(timezone.utc)
    expire = _now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": _now,  # FIX: [2026-07-16 P0-A] 同步添加 iat 声明
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
                _env = (settings.APP_ENV or "dev").lower()
                logger.warning(f"Redis token revocation check failed for user {user_id}: {e}")
                if _env in {"prod", "production"}:
                    raise jwt.InvalidTokenError("Token revocation check unavailable (Redis down)")
                # 非生产环境降级放行
    return payload
