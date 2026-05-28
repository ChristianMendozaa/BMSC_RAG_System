import uuid
from datetime import datetime, timezone

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
        iat_raw = payload.get("iat")
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

    # Bloquear sesiones residuales tras reset de contraseña o reactivación:
    # cualquier token emitido antes de tokens_valid_after se considera inválido.
    if user.tokens_valid_after is not None and iat_raw is not None:
        try:
            issued_at = datetime.fromtimestamp(int(iat_raw), tz=timezone.utc)
        except (TypeError, ValueError):
            raise credentials_exception
        if issued_at < user.tokens_valid_after:
            raise credentials_exception

    # Usuario sin rol no puede operar — login lo bloquea, esta es la defensa
    # secundaria si un token quedó vivo cuando se le quitó el rol.
    if user.role_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta no tiene rol asignado. Contacte al administrador.",
        )

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
