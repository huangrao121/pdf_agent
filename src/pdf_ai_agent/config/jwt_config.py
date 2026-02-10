from pydantic import BaseModel, Field

class JWTConfig(BaseModel):
    """
    JWT 配置类，用于管理 JWT 相关的设置。
    """
    active_kid: str = Field(..., description="当前使用的密钥 ID")
    jwt_private_key: str = Field(..., description="JWT 私钥，用于签名令牌")
    key_set: dict = Field(..., description="密钥集，包含多个公钥用于验证令牌")

    @classmethod
    def from_env(cls) -> "JWTConfig":
        """
        从环境变量加载 JWT 配置。

        环境变量:
            JWT_ACTIVE_KID: 当前使用的密钥 ID
            JWT_PRIVATE_KEY: JWT 私钥
            JWT_KEYSET: 密钥集，JSON 格式

        返回:
            JWTConfig 实例
        """
        import os
        import json

        active_kid = os.getenv("JWT_ACTIVE_KID", "default-key")
        jwt_private_key = os.getenv("JWT_PRIVATE_KEY", "")
        keyset_json = os.getenv("JWT_KEYSET", "{}")

        if not jwt_private_key:
            raise ValueError("JWT_PRIVATE_KEY environment variable is required")
        
        keyset = json.loads(keyset_json)

        return cls(
            active_kid=active_kid,
            jwt_private_key=jwt_private_key,
            key_set=keyset
        )
