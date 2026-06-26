import asyncio
import secrets
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
    RequestPasswordResetRequest,
    ConfirmPasswordResetRequest,
)
from app.db.session import get_pg_db
from app.dependencies import get_current_user, oauth2_scheme
from app.services.email_service import (
    notify_account_locked,
    notify_password_reset_code,
    notify_verification_code,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

CODE_EXPIRY_MINUTES = 15
CODE_RESEND_COOLDOWN_SECONDS = 60
MAX_CODE_ATTEMPTS = 5
PURPOSE_FIRST_LOGIN = "first_login"
PURPOSE_PASSWORD_RESET = "password_reset"


def _make_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _clear_verification_code(user: PGUser) -> None:
    user.verification_code = None
    user.verification_code_hash = None
    user.verification_code_expires_at = None
    user.verification_code_attempts = 0
    user.verification_code_sent_at = None
    user.verification_code_purpose = None


def _set_verification_code(user: PGUser, code: str, purpose: str, now: datetime) -> None:
    user.verification_code = None
    user.verification_code_hash = get_password_hash(code)
    user.verification_code_expires_at = now + timedelta(minutes=CODE_EXPIRY_MINUTES)
    user.verification_code_attempts = 0
    user.verification_code_sent_at = now
    user.verification_code_purpose = purpose


def _cooldown_active(user: PGUser, now: datetime) -> bool:
    if user.verification_code_sent_at is None:
        return False
    return user.verification_code_sent_at + timedelta(seconds=CODE_RESEND_COOLDOWN_SECONDS) > now


def _validate_verification_code(user: PGUser, code: str, purpose: str, now: datetime) -> None:
    if user.verification_code_purpose != purpose or not user.verification_code_hash:
        raise HTTPException(status_code=400, detail="Código de verificación incorrecto")
    if not user.verification_code_expires_at or user.verification_code_expires_at < now:
        raise HTTPException(status_code=400, detail="El código de verificación ha expirado")
    if user.verification_code_attempts >= MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Demasiados intentos. Solicite un nuevo código")
    if not verify_password(code, user.verification_code_hash):
        user.verification_code_attempts += 1
        raise HTTPException(status_code=400, detail="Código de verificación incorrecto")


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

    now = datetime.now(timezone.utc)
    if _cooldown_active(user, now):
        raise HTTPException(status_code=429, detail="Espere antes de solicitar otro código")

    code = _make_code()
    _set_verification_code(user, code, PURPOSE_FIRST_LOGIN, now)
    await db.commit()

    sent = await notify_verification_code(
        to_addr=user.email,
        username=user.username,
        code=code,
        expires_minutes=CODE_EXPIRY_MINUTES,
    )
    if not sent:
        _clear_verification_code(user)
        await db.commit()
        raise HTTPException(status_code=503, detail="No se pudo enviar el código de verificación")


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

    now = datetime.now(timezone.utc)
    try:
        _validate_verification_code(user, body.code, PURPOSE_FIRST_LOGIN, now)
    except HTTPException:
        await db.commit()
        raise

    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 4 caracteres")

    # Todo correcto: cambiar password y limpiar el requerimiento
    user.hashed_password = get_password_hash(body.new_password)
    user.must_change_password = False
    _clear_verification_code(user)
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


@router.post("/request-password-reset", status_code=204)
async def request_password_reset(
    body: RequestPasswordResetRequest,
    db: AsyncSession = Depends(get_pg_db),
):
    """Envía un código de recuperación sin revelar si el correo existe."""
    ident = body.identifier.strip()
    now = datetime.now(timezone.utc)
    user = await db.scalar(
        select(PGUser).where(func.lower(PGUser.email) == ident.lower())
    )

    if not user or not user.email or not user.is_active:
        return

    if _cooldown_active(user, now):
        return

    code = _make_code()
    _set_verification_code(user, code, PURPOSE_PASSWORD_RESET, now)
    await db.commit()

    sent = await notify_password_reset_code(
        to_addr=user.email,
        username=user.username,
        code=code,
        expires_minutes=CODE_EXPIRY_MINUTES,
    )
    if not sent:
        _clear_verification_code(user)
        await db.commit()
        raise HTTPException(status_code=503, detail="No se pudo enviar el código de recuperación")


@router.post("/confirm-password-reset", response_model=LoginResponse)
async def confirm_password_reset(
    body: ConfirmPasswordResetRequest,
    db: AsyncSession = Depends(get_pg_db),
):
    """Valida el código enviado por correo y define una nueva contraseña."""
    ident = body.identifier.strip()
    user = await db.scalar(
        select(PGUser).where(func.lower(PGUser.email) == ident.lower())
    )
    if not user or not user.email or not user.is_active:
        raise HTTPException(status_code=400, detail="Código de verificación incorrecto")

    now = datetime.now(timezone.utc)
    try:
        _validate_verification_code(user, body.code, PURPOSE_PASSWORD_RESET, now)
    except HTTPException:
        await db.commit()
        raise

    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 4 caracteres")

    user.hashed_password = get_password_hash(body.new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    user.tokens_valid_after = now
    _clear_verification_code(user)
    await db.commit()

    jti = uuid.uuid4()
    token = create_access_token(user_id=user.id, jti=jti)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserInfo.model_validate(user),
    )
