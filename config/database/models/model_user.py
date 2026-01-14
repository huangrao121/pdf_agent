from models.model_base import Base, TimestampMixin

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, Boolean

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from models.model_document import DocsModel, NoteModel, ChatSessionModel, JobModel

class UserModel(Base, TimestampMixin):
    """用户模型 - 系统用户账户
    
    管理用户身份、权限和所有权关系。
    
    设计要点:
    - username 和 email 都是唯一标识
    - is_active：软删除标记，禁用而非删除用户
    - is_superuser：管理员权限标记
    - 作为 workspace、document、note、session 的所有者
    - 通过 workspace 实现多租户隔离
    """
    __tablename__ = 'users'

    # 主键
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 身份信息
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)  # 用户名（登录用）
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)  # 邮箱
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 全名/显示名称
    
    # 权限标记
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 账户是否激活
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否为超级管理员

    # Relationships
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