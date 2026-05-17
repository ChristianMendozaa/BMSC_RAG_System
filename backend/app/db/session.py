from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

pg_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": False},
)

PGAsyncSessionLocal = async_sessionmaker(
    pg_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_pg_db():
    async with PGAsyncSessionLocal() as session:
        yield session
