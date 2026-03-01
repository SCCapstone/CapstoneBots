from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import sqlalchemy as sa
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
import ssl

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/capstonebots"
)

# Fix the driver name for async
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Fix the SSL argument for asyncpg
# Remove '?sslmode=require' if it exists to prevent the TypeError
if "?sslmode=" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split("?")[0]

# Determine if SSL context should be passed for DigitalOcean databases
connect_args = {}
if "ondigitalocean.app" in DATABASE_URL or "db.ondigitalocean.com" in DATABASE_URL:
    # Create a custom SSL context to handle DO's self-signed certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connect_args = {"ssl": ssl_context}

# Create async engine with connection pooling
engine = create_async_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.getenv("SQL_ECHO", "False") == "True",
    pool_size=int(os.getenv("DB_POOL_SIZE", 20)),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 10)),
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600  # Recycle connections every hour
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

# Dependency for FastAPI routes
async def get_db() -> AsyncSession:
    """Dependency to inject database session into FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Lifecycle management
async def init_db():
    """Initialize database connection and create tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Ensure nullable columns for account deletion (idempotent)
        for stmt in [
            "ALTER TABLE branches ALTER COLUMN created_by DROP NOT NULL",
            "ALTER TABLE commits ALTER COLUMN author_id DROP NOT NULL",
        ]:
            try:
                await conn.execute(sa.text(stmt))
            except Exception:
                pass  # Column already nullable

async def close_db():
    """Close database connections."""
    await engine.dispose()