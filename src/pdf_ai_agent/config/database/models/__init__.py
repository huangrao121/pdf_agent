"""
Models package - 集中导入所有数据库模型

这个文件的目的是确保所有模型类都被导入，这样 SQLAlchemy 的 Base.metadata
才能收集到所有表的定义。

导入顺序很重要，避免循环依赖：
1. base (基类)
2. auth (认证模型)
3. user (用户和工作空间)
4. document (文档相关模型)
"""

# 1. 导入 Base 基类
from pdf_ai_agent.config.database.models.model_base import (
    Base,
    TimestampMixin,
    CreatedMixin,
)

# 2. 导入认证模型
from pdf_ai_agent.config.database.models.model_auth import (
    OAuthIdentityModel,
    PasswordCredentialModel,
    VerificationCodeModel,
    OAuthProviderEnum,
    VerificationCodeTypeEnum,
)

# 3. 导入用户和工作空间模型
from pdf_ai_agent.config.database.models.model_user import (
    UserModel,
    WorkspaceModel,
)

# 4. 导入文档相关模型
from pdf_ai_agent.config.database.models.model_document import (
    DocsModel,
    ChunksModel,
    NoteModel,
    AnchorModel,
    ChatSessionModel,
    MessageModel,
    JobModel,
    DocStatus,
    RoleEnum,
    JobTypeEnum,
    JobStatusEnum,
)

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "CreatedMixin",
    # Auth models
    "OAuthIdentityModel",
    "PasswordCredentialModel",
    "VerificationCodeModel",
    "OAuthProviderEnum",
    "VerificationCodeTypeEnum",
    # User models
    "UserModel",
    "WorkspaceModel",
    # Document models
    "DocsModel",
    "ChunksModel",
    "NoteModel",
    "AnchorModel",
    "ChatSessionModel",
    "MessageModel",
    "JobModel",
    # Enums
    "DocStatus",
    "RoleEnum",
    "JobTypeEnum",
    "JobStatusEnum",
]
