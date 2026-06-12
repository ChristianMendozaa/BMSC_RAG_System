import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, decode_token, verify_password
from app.db.models.revoked_token import RevokedToken
from app.db.models.user import PGUser
from app.db.schemas.auth import LoginRequest, LoginResponse, MeResponse, UserInfo
from app.db.session import get_pg_db
from app.dependencies import get_current_user, oauth2_scheme

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_pg_db),
):
    # Primero buscar por correo (usuarios normales)
    ident = body.identifier.strip()
    user = await db.scalar(
        select(PGUser).where(func.lower(PGUser.email) == ident.lower())
    )
    # Si no se encontró por correo, permitir login por username solo para usuarios del sistema (is_system=True)
    if user is None:
        user = await db.scalar(
            select(PGUser).where(
                PGUser.username == ident,
                PGUser.is_system.is_(True),
            )
        )

    now = datetime.now(timezone.utc)

    # Cuenta bloqueada por intentos fallidos: rechazar sin verificar la contraseña.
    if user and user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Cuenta bloqueada por intentos fallidos. "
                f"Intente nuevamente en {remaining} minuto(s)."
            ),
        )

    if not user or not verify_password(body.password, user.hashed_password):
        # Los usuarios del sistema (admin default) nunca se bloquean: evita
        # que intentos maliciosos dejen el sistema sin administrador.
        if user and not user.is_system:
            result = await db.execute(
                update(PGUser)
                .where(PGUser.id == user.id)
                .values(failed_login_attempts=PGUser.failed_login_attempts + 1)
                .returning(PGUser.failed_login_attempts)
            )
            attempts = result.scalar_one()
            if attempts >= settings.max_login_attempts:
                await db.execute(
                    update(PGUser)
                    .where(PGUser.id == user.id)
                    .values(
                        failed_login_attempts=0,
                        locked_until=now + timedelta(minutes=settings.lockout_minutes),
                    )
                )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    # Login exitoso: limpiar contador y bloqueo expirado si quedaron seteados.
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo",
        )
    if user.role_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta no tiene rol asignado. Contacte al administrador.",
        )

    jti = uuid.uuid4()
    token = create_access_token(user_id=user.id, jti=jti)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserInfo.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: PGUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_pg_db),
):
    from jose import JWTError

    try:
        payload = decode_token(token)
        jti = uuid.UUID(payload["jti"])
        exp_ts = payload["exp"]
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    except (JWTError, KeyError, ValueError):
        return

    revoked = RevokedToken(
        jti=jti,
        user_id=current_user.id,
        expires_at=expires_at,
    )
    db.add(revoked)
    await db.commit()


@router.get("/me", response_model=MeResponse)
async def me(current_user: PGUser = Depends(get_current_user)):
    return current_user
