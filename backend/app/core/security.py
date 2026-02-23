from datetime import datetime, timedelta, timezone
import uuid
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)



def _create_token(data: dict, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    to_encode["iat"] = int(now.timestamp())
    to_encode["exp"] = int((now + expires_delta).timestamp())
    if "jti" not in to_encode:
        to_encode["jti"] = uuid.uuid4().hex

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )


def create_access_token(data: dict, expires_delta: int | None = None):
    minutes = expires_delta if expires_delta is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload = data.copy()
    payload["token_type"] = "access"
    return _create_token(payload, timedelta(minutes=minutes))


def create_refresh_token(data: dict, expires_days: int = 7):
    payload = data.copy()
    payload["token_type"] = "refresh"
    return _create_token(payload, timedelta(days=expires_days))


def decode_token(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None
