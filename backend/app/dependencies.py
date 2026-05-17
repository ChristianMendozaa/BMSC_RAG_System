import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models.revoked_token import RevokedToken
from app.db.models.user import PGUser
from app.db.session import get_pg_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_pg_db),
) -> PGUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id_str: str | None = payload.get("sub")
        jti_str: str | None = payload.get("jti")
        if user_id_str is None or jti_str is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        jti = uuid.UUID(jti_str)
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    revoked = await db.scalar(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    if revoked is not None:
        raise credentials_exception

    user = await db.scalar(
        select(PGUser).where(PGUser.id == user_id)
    )
    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: PGUser = Depends(get_current_user),
) -> PGUser:
    return current_user


async def get_current_admin_user(
    current_user: PGUser = Depends(get_current_user),
) -> PGUser:
    if not current_user.role.can_manage_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user
