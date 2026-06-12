import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_password_hash
from app.db.models.role import PGRole
from app.db.models.user import PGUser

logger = logging.getLogger(__name__)

# Migración in-place para BDs existentes (bd.sql ya las trae en instalaciones nuevas).
# ADD COLUMN IF NOT EXISTS es idempotente: seguro de ejecutar en cada arranque.
_LOCKOUT_DDL = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INT NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ",
)


async def ensure_lockout_columns(db: AsyncSession) -> None:
    for stmt in _LOCKOUT_DDL:
        await db.execute(text(stmt))
    await db.commit()
    logger.info("✓ Columnas de bloqueo de login verificadas")


async def seed_initial_admin(db: AsyncSession) -> None:
    count = await db.scalar(select(func.count()).select_from(PGUser))
    if count and count > 0:
        logger.info("✓ Usuarios existentes, seed omitido")
        return

    result = await db.execute(select(PGRole).where(PGRole.name == "SUPERADMIN"))
    superadmin_role = result.scalar_one_or_none()
    if not superadmin_role:
        logger.error("✗ Rol SUPERADMIN no encontrado en PostgreSQL — ejecuta bd.sql primero")
        return

    admin_user = PGUser(
        username=settings.initial_admin_username,
        hashed_password=get_password_hash(settings.initial_admin_password),
        role_id=superadmin_role.id,
        is_active=True,
        is_system=True,
    )
    db.add(admin_user)
    await db.commit()
    logger.info("✓ Usuario inicial creado: %s", settings.initial_admin_username)
