"""
Pytest configuration and fixtures for testing.
"""
import pytest
from sqlalchemy import event, BigInteger, Integer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.dialects.postgresql import JSONB

from pdf_ai_agent.config.database.models import Base

@event.listens_for(Base.metadata, "before_create")
def receive_before_create(target, connection, **kw):
    """
    Convert JSONB to JSON and BigInteger to Integer for SQLite compatibility.
    
    This listener is automatically triggered before creating tables.
    It converts PostgreSQL JSONB columns to SQLite JSON columns, 
    and BigInteger to Integer (for AUTOINCREMENT support).
    """
    if connection.dialect.name == "sqlite": 
        for table in target.tables.values():
            for column in table.columns:
                # Convert JSONB to JSON
                if isinstance(column.type, JSONB):
                    column.type = JSON()
                # Convert BigInteger to Integer for AUTOINCREMENT
                # SQLite's AUTOINCREMENT only works with INTEGER, not BIGINT
                if isinstance(column.type, BigInteger):
                    column.type = Integer()


@pytest.fixture(scope="function")
async def db_engine():
    """
    Create an in-memory SQLite database engine for testing.
    
    SQLite doesn't support PostgreSQL's JSONB type, so we register a type adapter
    to convert JSONB to JSON.
    
    Features:
    - In-memory database (no disk I/O)
    - Foreign keys enabled
    - SQLite-compatible type handling for JSONB fields
    
    Returns:
        AsyncEngine: SQLAlchemy async engine
    """
    # Create in-memory SQLite engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,  # Set to True for debugging SQL queries
        poolclass=StaticPool,  # Use StaticPool for in-memory database
        connect_args={"timeout": 5},
    )
    
    # Enable foreign key support in SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def sqlite_fk_support(dbapi_connection, connection_record):
        """Enable foreign key constraints in SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Register type adapter to handle PostgreSQL JSONB in SQLite
    # SQLite will store JSONB as JSON (TEXT)
    @event.listens_for(engine.sync_engine, "connect")
    def sqlite_jsonb_support(dbapi_connection, connection_record):
        """
        SQLite doesn't have native JSONB support like PostgreSQL.
        This adapter allows JSONB columns to work as JSON in SQLite.
        """
        # SQLite will just store JSON as TEXT, which is compatible
        # No special handling needed - SQLAlchemy will handle the conversion
        pass
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup: dispose of engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine):
    """
    Create a database session for testing.
    
    Provides an AsyncSession that automatically rolls back after each test
    to ensure test isolation.
    
    Returns:
        AsyncSession: SQLAlchemy async session
    """
    # Create session factory
    AsyncSessionLocal = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Create session
    async with AsyncSessionLocal() as session:
        yield session
        # Auto-rollback on fixture teardown for test isolation
        await session.rollback()