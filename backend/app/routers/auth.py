import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    user = await db.scalar(
        select(PGUser).where(PGUser.username == body.username)
    )

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo",
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
