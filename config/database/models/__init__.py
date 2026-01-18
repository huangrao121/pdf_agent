# Import all models to ensure they are registered with SQLAlchemy
from database.models.model_base import Base, TimestampMixin, CreatedMixin
from database.models.model_user import UserModel, WorkspaceModel
from database.models.model_document import (
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
from database.models.model_auth import (
    OAuthIdentityModel,
    PasswordCredentialModel,
    VerificationCodeModel,
    VerificationCodeType,
)

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "CreatedMixin",
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
    "DocStatus",
    "RoleEnum",
    "JobTypeEnum",
    "JobStatusEnum",
    # Auth models
    "OAuthIdentityModel",
    "PasswordCredentialModel",
    "VerificationCodeModel",
    "VerificationCodeType",
]
