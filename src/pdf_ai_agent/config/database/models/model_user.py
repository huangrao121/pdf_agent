from pdf_ai_agent.config.database.models.model_base import Base, TimestampMixin

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Boolean

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from pdf_ai_agent.config.database.models.model_document import DocsModel, NoteModel, ChatSessionModel, JobModel
    from pdf_ai_agent.config.database.models.model_auth import OAuthIdentityModel, PasswordCredentialModel, VerificationCodeModel

class UserModel(Base, TimestampMixin):
    """用户模型 - 系统用户账户（用户档案信息）
    
    存储用户的档案信息和权限，不包含认证凭据。
    认证凭据存储在独立的表中：
    - OAuth 登录：oauth_identities 表
    - 邮箱密码登录：password_credentials 表
    - 验证码：verification_codes 表
    
    设计要点:
    - username 是唯一标识
    - email 可选（某些 OAuth 用户可能不提供 email）
    - is_active：软删除标记，禁用而非删除用户
    - is_superuser：管理员权限标记
    - 作为 workspace、document、note、session 的所有者
    - 通过 workspace 实现多租户隔离
    - 不存储密码或 OAuth token（由独立的 auth 表管理）
    """
    __tablename__ = 'users'

    # 主键
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 档案信息（用户资料，不包含认证凭据）
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)  # 用户名（唯一标识）
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)  # 邮箱（可选，OAuth用户可能无email）
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 全名/显示名称
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # 头像URL
    
    # 权限标记
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 账户是否激活
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否为超级管理员
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 邮箱是否验证

    # Relationships - Document ownership
    documents: Mapped[list["DocsModel"]] = relationship(
        "DocsModel",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["NoteModel"]] = relationship(
        "NoteModel",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["ChatSessionModel"]] = relationship(
        "ChatSessionModel",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    workspaces: Mapped[list["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    # Relationships - Authentication
    oauth_identities: Mapped[list["OAuthIdentityModel"]] = relationship(
        "OAuthIdentityModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_credential: Mapped[Optional["PasswordCredentialModel"]] = relationship(
        "PasswordCredentialModel",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,  # 1:1 relationship
    )
    verification_codes: Mapped[list["VerificationCodeModel"]] = relationship(
        "VerificationCodeModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class WorkspaceModel(Base, TimestampMixin):
    """工作空间模型 - 多租户隔离的基本单位
    
    Workspace 是数据隔离的边界，每个用户可以有多个 workspace。
    所有文档、笔记、会话都属于某个 workspace。
    
    设计要点:
    - 实现多租户数据隔离
    - 支持团队协作（未来可添加成员表）
    - 作为权限控制的第一层
    - 所有 workspace 级别的配置都存在这里
    """
    __tablename__ = 'workspaces'

    # 主键
    workspace_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 基本信息
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 工作空间名称
    
    # 外键 - 所有者
    owner_user_id: Mapped[BigInteger] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)

    # Relationships
    owner: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="workspaces",
    )
    documents: Mapped[list["DocsModel"]] = relationship(
        "DocsModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["NoteModel"]] = relationship(
        "NoteModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["ChatSessionModel"]] = relationship(
        "ChatSessionModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["JobModel"]] = relationship(
        "JobModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )