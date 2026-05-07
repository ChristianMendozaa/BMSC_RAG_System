import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _get_db_url() -> str:
    path = settings.sqlite_path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


engine = create_async_engine(_get_db_url(), echo=False)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
