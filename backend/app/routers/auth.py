import asyncio
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, decode_token, verify_password, get_password_hash
from app.db.models.revoked_token import RevokedToken
from app.db.models.user import PGUser
from app.db.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    UserInfo,
    SendVerificationCodeRequest,
    VerifyFirstLoginRequest,
)
from app.db.session import get_pg_db
from app.dependencies import get_current_user, oauth2_scheme
from app.services.email_service import notify_account_locked, notify_verification_code

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
                locked_until = now + timedelta(minutes=settings.lockout_minutes)
                await db.execute(
                    update(PGUser)
                    .where(PGUser.id == user.id)
                    .values(
                        failed_login_attempts=0,
                        locked_until=locked_until,
                    )
                )
                await db.commit()
                # Notificación de bloqueo (best-effort, no bloquea la respuesta)
                if user.email:
                    asyncio.create_task(
                        notify_account_locked(
                            to_addr=user.email,
                            username=user.username,
                            lockout_minutes=settings.lockout_minutes,
                        )
                    )
            else:
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

    # Bloquear login normal si debe cambiar su contraseña (primer login)
    if getattr(user, "must_change_password", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="must_change_password",
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


@router.post("/send-verification-code", status_code=204)
async def send_verification_code(
    body: SendVerificationCodeRequest,
    db: AsyncSession = Depends(get_pg_db),
):
    """Envía un código de 6 dígitos al correo del usuario para el primer login."""
    ident = body.identifier.strip()
    user = await db.scalar(
        select(PGUser).where(func.lower(PGUser.email) == ident.lower())
    )
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not getattr(user, "must_change_password", False):
        raise HTTPException(status_code=400, detail="El usuario no requiere cambio de contraseña")

    if not user.email:
        raise HTTPException(status_code=400, detail="El usuario no tiene correo registrado")

    code = "".join(random.choices(string.digits, k=6))
    user.verification_code = code
    user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db.commit()

    asyncio.create_task(
        notify_verification_code(
            to_addr=user.email,
            username=user.username,
            code=code,
        )
    )


@router.post("/verify-first-login", response_model=LoginResponse)
async def verify_first_login(
    body: VerifyFirstLoginRequest,
    db: AsyncSession = Depends(get_pg_db),
):
    """Verifica el código de 6 dígitos y cambia la contraseña, retornando el token de login."""
    ident = body.identifier.strip()
    user = await db.scalar(
        select(PGUser).where(func.lower(PGUser.email) == ident.lower())
    )
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not getattr(user, "must_change_password", False):
        raise HTTPException(status_code=400, detail="El usuario no requiere cambio de contraseña")

    if not user.verification_code or user.verification_code != body.code:
        raise HTTPException(status_code=400, detail="Código de verificación incorrecto")

    now = datetime.now(timezone.utc)
    if not user.verification_code_expires_at or user.verification_code_expires_at < now:
        raise HTTPException(status_code=400, detail="El código de verificación ha expirado")

    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 4 caracteres")

    # Todo correcto: cambiar password y limpiar el requerimiento
    user.hashed_password = get_password_hash(body.new_password)
    user.must_change_password = False
    user.verification_code = None
    user.verification_code_expires_at = None
    user.tokens_valid_after = now
    await db.commit()

    # Generar token y loguear automáticamente
    jti = uuid.uuid4()
    token = create_access_token(user_id=user.id, jti=jti)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserInfo.model_validate(user),
    )
