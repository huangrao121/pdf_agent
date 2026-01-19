from typing import AsyncGenerator
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from functools import lru_cache

from pdf_ai_agent.config.database.models.model_base import Base

Base = Base()

class DatabaseConfig(BaseSettings):
    """
    DatabaseConfig 的 Docstring
    """
    database_type: str = Field(..., description="数据库类型，如 'sqlite', 'postgresql', 'mysql' 等")
    database_username: str = Field(default="", description="数据库用户名")
    database_password: str = Field(default="", description="数据库密码")
    database_host: str = Field(default="", description="数据库主机地址")
    database_port: int = Field(default=0, description="数据库端口号")
    database_name: str = Field(..., description="数据库名称")

    model_config = ConfigDict(
        case_sensitive = False,
        extra = "ignore"
    )

@lru_cache()
def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(_env_file=".env.local")

async def init_database(config: DatabaseConfig):
    """
    初始化数据库连接的异步生成器函数。

    参数:
        config (DatabaseConfig): 数据库配置对象。

    生成:
        AsyncGenerator[None, None]: 异步生成器，初始化完成后生成 None。
    """
    # Import user model to ensure it's registered with SQLAlchemy
    # Note: model_document has issues and is not needed for basic auth functionality
    from pdf_ai_agent.config.database.models import model_user
    
    # 在这里添加数据库初始化逻辑，例如创建连接池等
    global _engine, _session
    
    # Build database URL based on type
    if config.database_type.startswith('sqlite'):
        # SQLite URL format: sqlite+aiosqlite:///:memory: or sqlite+aiosqlite:///path/to/db.db
        if config.database_name == ":memory:":
            url = f"{config.database_type}:///:memory:"
        else:
            url = f"{config.database_type}:///{config.database_name}"
    else:
        # PostgreSQL/MySQL URL format
        url = f"{config.database_type}://{config.database_username}:{config.database_password}@{config.database_host}:{config.database_port}/{config.database_name}"
    
    try:
        _engine = create_async_engine(url)
        _session = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    except Exception as e:
        print(f"数据库初始化失败: {e}")
        raise
    # 在这里添加数据库关闭逻辑，例如关闭连接池等
    # 例如:
    # await engine.dispose()

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    异步生成器函数，提供数据库会话。

    生成:
        AsyncGenerator[AsyncSession, None]: 异步生成器，生成数据库会话对象。
    """
    async with _session() as session:
        yield session

async def close_engine():
    """
    关闭数据库引擎连接池的异步函数。
    """
    try:
        if _engine is not None:
            await _engine.dispose()
    except Exception as e:
        print(f"关闭数据库引擎失败: {e}")
        raise