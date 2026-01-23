from sqlalchemy import Integer, String, Text, ForeignKey, Boolean
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.dialects.postgresql import BIGINT as BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    Enum,
    Any
)
from sqlalchemy import Index

from enum import Enum as PyEnum

from typing import Optional, Dict, TYPE_CHECKING

from pdf_ai_agent.config.database.models.model_base import Base, TimestampMixin, CreatedMixin

if TYPE_CHECKING:
    from pdf_ai_agent.config.database.models.model_user import UserModel, WorkspaceModel

class DocStatus(PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class DocsModel(Base, TimestampMixin):
    """文档模型 - 存储上传的 PDF 文档元数据
    
    这是系统的核心实体之一，代表用户上传的 PDF 文档。
    每个文档必须属于一个 workspace 和一个 owner。
    通过 file_sha256 确保同一文档不会在同一 workspace 中重复存储。
    
    设计要点:
    - 使用 file_sha256 作为去重标识
    - 支持文档处理状态跟踪 (UPLOADED -> PROCESSING -> PROCESSED/ERROR)
    - 记录分块和嵌入模型版本，便于重新索引
    - 关联 chunks（分块）、notes（笔记）、anchors（锚点）
    """
    __tablename__ = 'doc'
    __table_args__ = (
        # 复合唯一索引：同一 workspace 中不能有相同 SHA256 的文档
        Index('idx_docs_workspace_filehash', 'workspace_id', 'file_sha256', unique=True),
    )

    # 主键
    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键 - 所属关系
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey('workspaces.workspace_id'), nullable=False, index=True)
    owner_user_id: Mapped[BigInteger] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)

    # 文件基本信息
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 原始文件名
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)  # 对象存储路径 (e.g., s3://bucket/path)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # MIME 类型 (e.g., application/pdf)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 文件大小（字节）
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # 文件内容哈希，用于去重

    # 文档元数据（从 PDF 提取或用户填写）
    title: Mapped[str] = mapped_column(String(255), nullable=True)  # 文档标题
    author: Mapped[str] = mapped_column(String(255), nullable=True)  # 作者
    description: Mapped[str] = mapped_column(Text, nullable=True)  # 文档描述/摘要
    language: Mapped[str] = mapped_column(String(50), nullable=True)  # 语言代码 (e.g., en, zh)
    num_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # PDF 总页数

    # 处理状态
    status: Mapped[str] = mapped_column(
        Enum(DocStatus, values_callable=lambda x: [e.value for e in x]), 
        nullable=False, 
        default=DocStatus.UPLOADED
    )  # 文档处理状态：uploaded -> processing -> processed/error
    error_message: Mapped[str] = mapped_column(Text, nullable=True)  # 处理失败时的错误信息

    # 版本控制信息（用于重新索引和升级）
    chucker_version: Mapped[str] = mapped_column(
        String(50), nullable=True, server_default="v1"
    )  # 分块算法版本，变更时可触发重新分块
    embed_model: Mapped[str] = mapped_column(String(100), nullable=True)  # 嵌入模型名称 (e.g., text-embedding-3-small)
    embed_dim: Mapped[int] = mapped_column(Integer, nullable=True)  # 嵌入向量维度 (e.g., 1536)

    #Relationships
    owner: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="documents",
    )
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="documents",
    )
    chunks: Mapped[list["ChunksModel"]] = relationship(
        "ChunksModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["NoteModel"]] = relationship(
        "NoteModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    anchors: Mapped[list["AnchorModel"]] = relationship(
        "AnchorModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["JobModel"]] = relationship(
        "JobModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    pages: Mapped[list["DocPageModel"]] = relationship(
        "DocPageModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )


class DocPageModel(Base, CreatedMixin):
    """文档页面模型 - 存储 PDF 文档的页面元数据
    
    每个 PDF 文档包含多个页面，此模型存储每页的基本信息。
    用于快速获取页面尺寸、旋转等元数据，无需重新解析 PDF。
    
    设计要点:
    - page 字段使用 1-based 索引（符合 PDF 规范和用户习惯）
    - 存储页面物理属性（宽、高、旋转）
    - text_layer_available 标识该页是否有可提取文本（非扫描件）
    - 通过 DOC_PARSE_METADATA 作业填充
    """
    __tablename__ = 'doc_page'
    __table_args__ = (
        # 复合唯一索引：doc_id + page 确保每页唯一
        Index('idx_doc_pages_doc_id_page', 'doc_id', 'page', unique=True),
    )

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键 - 所属文档
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc.doc_id'), nullable=False, index=True)

    # 页面信息
    page: Mapped[int] = mapped_column(Integer, nullable=False)  # 页码（1-based）
    width_pt: Mapped[float] = mapped_column(Integer, nullable=False)  # 页面宽度（点，1/72 英寸）
    height_pt: Mapped[float] = mapped_column(Integer, nullable=False)  # 页面高度（点）
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 旋转角度（0, 90, 180, 270）
    text_layer_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否有文本层
    
    # Relationships
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="pages",
    )


class ChunksModel(Base, TimestampMixin):
    """文档分块模型 - 存储文档的语义分块
    
    每个文档会被切分成多个 chunks，这是 RAG 检索的基本单位。
    Chunk 包含原始文本、位置信息（页码、偏移）、嵌入向量等。
    
    设计要点:
    - chunk_index 保证分块顺序，便于重建文档
    - text_sha256 用于检测文本变化，避免重复计算嵌入
    - 嵌入向量存储在 Neo4j，Postgres 只存文本和元数据
    - offsets/bboxes 用于在 PDF 中精确定位和高亮
    """
    __tablename__ = 'doc_chunk'
    __table_args__ = (
        # 复合唯一索引：doc_id + chunk_index 确保分块顺序唯一
        Index('idx_doc_chunks_doc_id_chunk_index', 'doc_id', 'chunk_index', unique=True),
        # 用于快速查找相同文本的分块（去重）
        Index('idx_doc_chunks_text_sha256', 'text_sha256'),
    )

    # 主键
    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    
    # 外键 - 所属文档
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc.doc_id'), nullable=False, index=True)

    # 分块顺序和位置
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 在文档中的顺序（从 0 开始）
    page_start: Mapped[int] = mapped_column(Integer, nullable=True)  # 起始页码
    page_end: Mapped[int] = mapped_column(Integer, nullable=True)  # 结束页码

    # 文本内容和结构
    section_path: Mapped[str] = mapped_column(Text, nullable=True)  # 章节路径 (e.g., "Chapter 1 > Section 1.1")
    text: Mapped[str] = mapped_column(Text, nullable=False)  # 分块文本内容
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # 文本哈希，用于去重
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)  # Token 数量（用于成本估算）

    # 精确定位信息（用于 PDF 高亮和跳转）
    offsets: Mapped[Optional[dict[str, int]]] = mapped_column(
        JSONB, nullable=True
    )  # 字符偏移量 {"page": 57, "start": 1234, "end": 1501}
    bboxes: Mapped[Optional[dict[str, list[int]]]] = mapped_column(
        JSONB, nullable=True
    )  # 边界框坐标 [{"page": 57, "x": 100, "y": 200, "w": 300, "h": 50}, ...]

    #Relationships
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="chunks",
    )
    anchors: Mapped[list["AnchorModel"]] = relationship(
        "AnchorModel",
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class NoteModel(Base, TimestampMixin):
    """笔记模型 - 用户针对文档创建的 Markdown 笔记
    
    笔记是用户的知识输出，可以包含：
    - 用户手写的文字
    - AI 生成的摘要和问答
    - 引用文档的锚点（Anchor）
    
    设计要点:
    - Markdown 格式，灵活扩展
    - 支持版本控制（version 字段）
    - 通过 Anchor 关联到文档的精确位置
    - 未来可作为二次检索源（笔记也可被搜索）
    """
    __tablename__ = 'doc_note'

    # 主键
    note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键 - 所属关系
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey('workspaces.workspace_id'), nullable=False, index=True)
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc.doc_id'), nullable=False, index=True)
    owner_user_id: Mapped[BigInteger] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)

    # 笔记内容
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # 笔记标题
    markdown: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown 格式的笔记正文
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )  # 版本号，支持未来的版本控制和协作编辑
    
    # Relationships
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="notes"
    )
    owner: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="notes",
    )
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="notes",
    )
    anchors: Mapped[list["AnchorModel"]] = relationship(
        "AnchorModel",
        back_populates="note",
        cascade="all, delete-orphan",
    )

class AnchorModel(Base, TimestampMixin):
    """锚点模型 - 连接笔记和文档的精确位置
    
    Anchor 是笔记引用原文的桥梁，记录：
    - 笔记引用了哪段文档内容
    - 在 PDF 的哪一页、哪个位置
    - 关联到哪个 chunk
    
    设计要点:
    - 多对多关系：一条笔记可以有多个锚点，一个 chunk 可以被多条笔记引用
    - quoted_text 存储用户选中的原文片段（用于显示）
    - locator 存储精确坐标（bbox/offset），用于 PDF 高亮和跳转
    - 支持点击笔记中的引用直接跳转到 PDF 对应位置
    """
    __tablename__ = 'doc_anchor'

    # 主键
    anchor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键 - 三方关联
    note_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc_note.note_id'), nullable=True, index=True)
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc.doc_id'), nullable=False, index=True)
    chunk_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc_chunk.chunk_id'), nullable=False, index=True)

    # 定位信息
    page: Mapped[int] = mapped_column(Integer, nullable=True)  # 页码（快速定位）
    quoted_text: Mapped[str] = mapped_column(
        Text, nullable=True
    )  # 用户引用的原文片段（用于在笔记中显示）
    locator: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )  # 精确定位器 {"bbox": {...}, "offset": {...}}，用于 PDF 高亮和跳转

    # Relationships
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="anchors",
    )
    note: Mapped["NoteModel"] = relationship(
        "NoteModel",
        back_populates="anchors",
    )
    chunk: Mapped["ChunksModel"] = relationship(
        "ChunksModel",
        back_populates="anchors",
    )

class ChatSessionModel(Base, CreatedMixin):
    """聊天会话模型 - 管理用户与 AI 的对话会话
    
    每个会话对应一次连续的对话，包含多条消息（MessageModel）。
    会话级别的上下文管理，支持未来的：
    - 会话摘要
    - 会话级设置（模型、温度等）
    - 会话分享和导出
    
    设计要点:
    - 只有 created_at（不需要 updated_at）
    - 属于某个 workspace，方便权限控制
    - 可关联多条 messages
    """
    __tablename__ = 'doc_chat_session'

    # 主键
    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键 - 所属关系
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey('workspaces.workspace_id'), nullable=False, index=True)
    owner_user_id: Mapped[BigInteger] = mapped_column(ForeignKey('users.user_id'), nullable=False, index=True)

    # Relationships
    owner: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="sessions",
    )
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="sessions",
    )
    messages: Mapped[list["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class RoleEnum(PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class MessageModel(Base, CreatedMixin):
    """消息模型 - 存储聊天会话中的每条消息
    
    包含用户提问、AI 回答、系统消息等。
    核心特性：
    - 存储完整的消息内容和角色
    - 记录引用信息（citation）：答案来自哪些文档/分块
    - 记录检索上下文（context）：RAG 检索到的相关信息
    
    设计要点:
    - sender_user_id 可为空（AI/系统消息）
    - citation 存储答案的来源，用于显示引用
    - context 存储检索上下文，用于调试和追溯
    - 支持未来的多轮对话和上下文管理
    """
    __tablename__ = 'doc_chat_message'
    __table_args__ = (
        # 复合索引：按会话和时间排序查询消息
        Index('idx_session_message', 'session_id', 'created_at'),
    )

    # 主键
    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc_chat_session.session_id'), nullable=False, index=True)
    sender_user_id: Mapped[BigInteger] = mapped_column(
        ForeignKey('users.user_id'), nullable=True, index=True
    )  # 发送者（AI/系统消息时为 NULL）

    # 消息内容
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 消息文本内容
    role: Mapped[str] = mapped_column(
        Enum(RoleEnum, values_callable=lambda x: [e.value for e in x]), 
        nullable=False
    )  # 角色：user（用户）、assistant（AI）、system（系统）、tool（工具）

    # RAG 相关信息
    citation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )  # 引用信息 [{"doc_id": 1, "chunk_id": 5, "page": 10, "quote": "..."}]
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )  # 检索上下文 {"query_embedding": [...], "retrieved_chunks": [...], "metadata": {...}}
    # Relationships
    session: Mapped["ChatSessionModel"] = relationship(
        "ChatSessionModel",
        back_populates="messages",
    )
    sender: Mapped["UserModel"] = relationship(
        "UserModel",
    )

class JobTypeEnum(PyEnum):
    INGEST_DOC = "ingest_document"
    REINDEX_DOC = "reindex_document"
    DELETE_DOC = "delete_document"
    DOC_PARSE_METADATA = "doc_parse_metadata"

class JobStatusEnum(PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class JobModel(Base, TimestampMixin):
    """异步任务模型 - 管理文档处理的后台任务
    
    用于跟踪异步执行的文档处理任务，如：
    - INGEST_DOC：文档导入（解析、分块、生成嵌入）
    - REINDEX_DOC：重新索引（更换嵌入模型、分块策略）
    - DELETE_DOC：删除文档及相关数据
    
    设计要点:
    - 支持重试机制（attempt/max_attempt）
    - 任务状态跟踪（pending -> in_progress -> completed/failed）
    - 存储任务参数（payload）和错误信息
    - Worker 从此表拉取任务执行
    - 支持进度跟踪，便于长时间任务的进度显示
    """
    __tablename__ = 'doc_processing_job'

    # 主键
    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 外键 - 关联文档和 workspace
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey('doc.doc_id'), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey('workspaces.workspace_id'), nullable=False, index=True)
    
    # 任务参数
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )  # 任务特定参数 {"chunk_size": 512, "embed_model": "...", ...}

    # 重试控制
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 当前尝试次数
    max_attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # 最大重试次数

    # 任务状态
    job_type: Mapped[str] = mapped_column(
        Enum(JobTypeEnum, values_callable=lambda x: [e.value for e in x]), 
        nullable=False
    )  # 任务类型：ingest_document, reindex_document, delete_document
    status: Mapped[str] = mapped_column(
        Enum(JobStatusEnum, values_callable=lambda x: [e.value for e in x]), 
        nullable=False, 
        default=JobStatusEnum.PENDING
    )  # 任务状态：pending, in_progress, completed, failed, canceled
    progress: Mapped[Optional[float]] = mapped_column(
        Integer, nullable=True
    )  # 进度百分比 0.0 - 100.0
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 失败时的错误信息

    # Relationships
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="jobs",
    )
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="jobs",
    )
