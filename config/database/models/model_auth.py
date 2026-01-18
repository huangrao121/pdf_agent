from database.models.model_base import Base, TimestampMixin

from sqlalchemy import Integer, ForeignKey, String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Boolean
from sqlalchemy import Enum
from enum import Enum as PyEnum

from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from database.models.model_user import UserModel


class OAuthIdentityModel(Base, TimestampMixin):
    """OAuth 身份模型 - 存储第三方 OAuth 登录信息
    
    支持用户通过第三方 OAuth 提供商（如 Google, GitHub, Microsoft）登录。
    一个用户可以关联多个 OAuth 身份，一个 OAuth 身份只能属于一个用户。
    
    设计要点:
    - (provider, provider_subject) 唯一标识一个 OAuth 身份
    - provider_subject 是 OAuth 提供商返回的用户唯一标识（sub 字段）
    - access_token 和 refresh_token 存储用于访问提供商 API（可选）
    - 支持账号绑定：同一用户可以关联多个 OAuth 提供商
    - 不存储密码，完全依赖 OAuth 提供商的身份验证
    """
    __tablename__ = 'oauth_identities'
    __table_args__ = (
        # 复合唯一索引：同一 OAuth 提供商的同一用户只能绑定一次
        Index('idx_oauth_provider_subject', 'provider', 'provider_subject', unique=True),
    )

    # 主键
    oauth_identity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键 - 关联用户
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)
    
    # OAuth 提供商信息
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # OAuth 提供商名称 (e.g., 'google', 'github', 'microsoft')
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)  # OAuth 提供商的用户唯一标识（sub 字段）
    
    # OAuth 令牌（可选，用于访问提供商 API）
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 访问令牌（已加密或哈希）
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 刷新令牌（已加密或哈希）
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 令牌过期时间
    
    # OAuth 用户信息（从提供商获取的额外信息）
    provider_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # OAuth 提供商返回的邮箱
    provider_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # OAuth 提供商返回的显示名称
    provider_avatar: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # OAuth 提供商返回的头像 URL
    
    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        foreign_keys=[user_id],
    )


class PasswordCredentialModel(Base, TimestampMixin):
    """密码凭证模型 - 存储邮箱密码登录信息
    
    支持传统的邮箱 + 密码登录方式。
    密码必须使用安全的哈希算法（如 bcrypt, argon2）存储，绝不存储明文密码。
    
    设计要点:
    - 一个用户只能有一个密码凭证（一对一关系）
    - password_hash 存储哈希后的密码，绝不存储明文
    - 支持邮箱验证（email_verified 标记）
    - 记录密码修改时间，用于强制定期更换密码等安全策略
    """
    __tablename__ = 'password_credentials'

    # 主键（同时也是外键，确保一对一关系）
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), primary_key=True)
    
    # 密码信息（存储哈希值）
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # 哈希后的密码（使用 bcrypt/argon2）
    
    # 邮箱验证
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 邮箱是否已验证
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 邮箱验证时间
    
    # 密码修改记录
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 最后一次修改密码时间
    
    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        foreign_keys=[user_id],
    )


class VerificationCodeType(PyEnum):
    """验证码类型枚举"""
    EMAIL_VERIFICATION = "email_verification"  # 邮箱验证
    PASSWORD_RESET = "password_reset"  # 密码重置
    CHANGE_EMAIL = "change_email"  # 更换邮箱


class VerificationCodeModel(Base, TimestampMixin):
    """验证码模型 - 统一管理各类验证令牌
    
    支持多种验证流程：
    - EMAIL_VERIFICATION：新用户注册后的邮箱验证
    - PASSWORD_RESET：忘记密码后的重置验证
    - CHANGE_EMAIL：用户更换邮箱的验证
    
    设计要点:
    - code_hash 存储哈希后的验证码，绝不存储明文（防止数据库泄露）
    - 每种类型可以有多个 active 的验证码（支持重发）
    - 使用 expires_at 控制验证码有效期（通常 15-30 分钟）
    - 使用后标记为 used_at，防止重复使用
    - 支持 metadata 字段存储额外信息（如新邮箱地址）
    """
    __tablename__ = 'verification_codes'
    __table_args__ = (
        # 复合索引：快速查找特定用户、类型、未使用的验证码
        Index('idx_verification_user_type_used', 'user_id', 'code_type', 'used_at'),
        # 索引：快速查找未过期的验证码
        Index('idx_verification_expires_at', 'expires_at'),
    )

    # 主键
    verification_code_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键 - 关联用户
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=False, index=True)
    
    # 验证码信息
    code_type: Mapped[str] = mapped_column(
        Enum(VerificationCodeType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )  # 验证码类型
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # 哈希后的验证码（使用 SHA256 或类似算法）
    
    # 有效期和使用状态
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 过期时间
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 使用时间（NULL 表示未使用）
    
    # 额外信息（JSON 格式存储）
    # 例如：更换邮箱时存储新邮箱地址 {"new_email": "new@example.com"}
    extra_data: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    
    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        foreign_keys=[user_id],
    )
