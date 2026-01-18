# Import all models to ensure they are registered with SQLAlchemy
from models.model_base import Base, TimestampMixin, CreatedMixin
from models.model_user import UserModel, WorkspaceModel
from models.model_document import (
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
from models.model_auth import (
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
