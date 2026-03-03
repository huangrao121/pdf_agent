from pydantic import BaseModel, Field
from typing import Optional
import os
from functools import lru_cache

class RedisConfig(BaseModel):
    host: str = Field(..., description="Redis server host")
    port: int = Field(..., description="Redis server port")
    db: int = Field(0, description="Redis database number")
    password: Optional[str] = Field(None, description="Password for Redis authentication")
    socket_connect_timeout: int = Field(5, description="Connection timeout in seconds")
    socket_timeout: Optional[int] = Field(None, description="Socket timeout in seconds")
    decode_responses: bool = Field(False, description="Decode responses as strings")
    max_connections: int = Field(50, description="Max connections in connection pool")

    @classmethod
    def from_env(cls):
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        db = int(os.getenv("REDIS_DB", 0))
        password = os.getenv("REDIS_PASSWORD", None)
        socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", 5))
        socket_timeout = os.getenv("REDIS_SOCKET_TIMEOUT")
        decode_responses = os.getenv("REDIS_DECODE_RESPONSES", "false").lower() == "true"
        max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))

        return cls(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=int(socket_timeout) if socket_timeout else None,
            decode_responses=decode_responses,
            max_connections=max_connections
        )


@lru_cache
def get_redis_config() -> RedisConfig:
    return RedisConfig.from_env()


# 单例 Redis 客户端
_redis_client = None


async def get_redis_client():
    """获取 Redis 客户端（异步）"""
    global _redis_client
    if _redis_client is None:
        from redis.asyncio import Redis
        config = get_redis_config()
        _redis_client = Redis(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password,
            socket_connect_timeout=config.socket_connect_timeout,
            socket_timeout=config.socket_timeout,
            decode_responses=config.decode_responses,
            max_connections=config.max_connections,
        )
    return _redis_client


async def close_redis_client():
    """关闭 Redis 客户端"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# 兼容同步用法（如有需要）
def init_redis_client_sync():
    """初始化同步 Redis 客户端"""
    from redis import Redis
    config = get_redis_config()
    return Redis(
        host=config.host,
        port=config.port,
        db=config.db,
        password=config.password,
        socket_connect_timeout=config.socket_connect_timeout,
        socket_timeout=config.socket_timeout,
        decode_responses=config.decode_responses,
        max_connections=config.max_connections,
    )