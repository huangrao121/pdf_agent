# 数据模型设计模式说明

## 📋 目录
1. [架构概览](#架构概览)
2. [设计模式](#设计模式)
3. [核心模型详解](#核心模型详解)
4. [关系图](#关系图)
5. [最佳实践](#最佳实践)

---

## 🏗️ 架构概览

这是一个基于 **SQLAlchemy 2.0** 的现代化数据模型设计，用于构建 **PDF 文档阅读 + RAG 问答 + Markdown 笔记** 系统。

### 核心理念

> **Postgres = Single Source of Truth**  
> **Neo4j = Derived Index (Rebuildable)**

- **Postgres**：存储所有业务数据、元数据、关系
- **Neo4j**：存储向量索引和图结构（可随时从 Postgres 重建）

### 技术栈

- **SQLAlchemy 2.0+** with `mapped_column` 和 `Mapped[]` 类型注解
- **AsyncIO** 支持（`AsyncAttrs`）
- **PostgreSQL 16+** with JSONB
- **Type Hints** 完全类型安全

---

## 🎨 设计模式

### 1. **Table-per-Class Pattern（每类一表）**

每个模型类对应一个独立的数据库表，清晰简单。

```python
class DocsModel(Base, TimestampMixin):
    __tablename__ = 'doc'  # 显式指定表名
```

**优点**：
- 结构清晰，易于理解
- 查询性能好
- 支持独立扩展

---

### 2. **Mixin Pattern（混入模式）**

使用 Mixin 提供可复用的字段和行为。

#### TimestampMixin
为模型自动添加创建时间和更新时间：

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

**使用场景**：需要追踪记录变更历史的模型（DocsModel、ChunksModel、NoteModel 等）

#### CreatedMixin
只添加创建时间（不需要更新时间）：

```python
class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
```

**使用场景**：不可变记录（ChatSessionModel、MessageModel）

**优点**：
- DRY（Don't Repeat Yourself）
- 统一的时间戳管理
- 便于未来扩展（如软删除 Mixin）

---

### 3. **Bidirectional Relationships（双向关系）**

使用 `back_populates` 建立双向引用，保持数据一致性。

```python
# 父表（一方）
class DocsModel:
    chunks: Mapped[list["ChunksModel"]] = relationship(
        "ChunksModel",
        back_populates="doc",
        cascade="all, delete-orphan",
    )

# 子表（多方）
class ChunksModel:
    doc: Mapped["DocsModel"] = relationship(
        "DocsModel",
        back_populates="chunks",
    )
```

**优点**：
- 双向导航：`doc.chunks` 和 `chunk.doc`
- 自动同步：修改一方会更新另一方
- 类型安全：IDE 自动补全

**为什么用 `back_populates` 而不是 `backref`？**
- `back_populates`：两边都显式声明，更清晰（推荐）
- `backref`：只写一边，更简洁但隐式

---

### 4. **Cascade Strategies（级联策略）**

定义删除和更新的传播行为。

```python
documents: Mapped[list["DocsModel"]] = relationship(
    "DocsModel",
    back_populates="owner",
    cascade="all, delete-orphan",
)
```

#### 级联类型说明

| 级联选项 | 含义 | 使用场景 |
|---------|------|---------|
| `all` | 包含 save-update, merge, refresh, expunge, delete | 强拥有关系 |
| `delete` | 删除父对象时删除子对象 | 父子生命周期一致 |
| `delete-orphan` | 子对象脱离父对象时自动删除 | 防止孤儿记录 |
| `save-update` | 保存父对象时自动保存子对象 | 默认行为 |
| 无级联 | 不传播任何操作 | 弱关联 |

**本项目的级联策略**：

- **强拥有关系**（`all, delete-orphan`）：
  - User → Documents
  - User → Notes  
  - User → Sessions
  - Doc → Chunks
  - Doc → Notes
  - Doc → Anchors
  - Session → Messages

- **弱关联**（无级联）：
  - Message → User（sender 可为空，不删除用户）

---

### 5. **Composite Index Pattern（复合索引）**

使用 `__table_args__` 定义复合索引和约束。

```python
class DocsModel(Base, TimestampMixin):
    __table_args__ = (
        # 复合唯一索引：同一 workspace 中不能有相同 SHA256 的文档
        Index('idx_docs_workspace_filehash', 'workspace_id', 'file_sha256', unique=True),
    )
```

**复合索引设计原则**：
1. **最左前缀原则**：高频查询字段放最左边
2. **唯一性约束**：业务去重逻辑通过 `unique=True` 实现
3. **覆盖索引**：包含查询所需的所有字段

**本项目的关键索引**：

| 表 | 索引 | 用途 |
|----|------|------|
| `doc` | `(workspace_id, file_sha256)` | 防止重复上传 |
| `doc_chunk` | `(doc_id, chunk_index)` | 保证分块顺序唯一 |
| `doc_chunk` | `(text_sha256)` | 快速查找相同内容 |
| `doc_chat_message` | `(session_id, created_at)` | 按时间排序消息 |

---

### 6. **String Reference Pattern（字符串引用模式）**

使用字符串引用避免循环导入。

```python
# model_user.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from models.model_document import DocsModel  # 只在类型检查时导入

class UserModel:
    documents: Mapped[list["DocsModel"]] = relationship(
        "DocsModel",  # 字符串引用，运行时解析
        back_populates="owner",
    )
```

**关键技巧**：
1. `TYPE_CHECKING`：只在静态类型检查时导入，避免运行时循环导入
2. `relationship()` 第一个参数用字符串
3. `Mapped[...]` 类型注解也用字符串

---

### 7. **JSONB for Flexibility（JSONB 灵活存储）**

使用 PostgreSQL 的 JSONB 类型存储半结构化数据。

```python
# 引用信息（结构可变）
citation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
    JSONB, nullable=True
)

# 精确定位器（不同文档格式不同）
locator: Mapped[Optional[dict[str, Any]]] = mapped_column(
    JSONB, nullable=True
)
```

**适用场景**：
- **结构可能变化**：citation, context, payload
- **嵌套数据**：bboxes（边界框数组）
- **可选扩展**：locator（不同文档类型有不同定位方式）

**优点**：
- 灵活性：无需修改表结构即可扩展
- 可索引：PostgreSQL 支持 JSONB 索引
- 类型安全：Python 端使用 `Dict[str, Any]`

**注意事项**：
- 不要滥用 JSONB，核心字段应该是列
- 可以为 JSONB 字段创建 GIN 索引提升查询性能

---

### 8. **Enum Pattern（枚举模式）**

使用 Python Enum 配合 SQLAlchemy Enum 实现类型安全的状态管理。

```python
# Python 枚举
class DocStatus(PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"

# 数据库字段
status: Mapped[str] = mapped_column(
    Enum(DocStatus, values_callable=lambda x: [e.value for e in x]),
    nullable=False,
    default=DocStatus.UPLOADED
)
```

**优点**：
- **类型安全**：IDE 检查，避免拼写错误
- **语义清晰**：`DocStatus.PROCESSING` vs `"processing"`
- **易于重构**：修改枚举值时 IDE 可全局替换

---

### 9. **Soft Delete Pattern（软删除模式）**

通过 `is_active` 标记而非物理删除。

```python
class UserModel:
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
```

**优点**：
- 可恢复
- 审计追踪
- 保持引用完整性

**实现方式**：
- 在查询时过滤 `is_active=True`
- 使用 SQLAlchemy 的 `Query.filter_by(is_active=True)`
- 或在模型中定义默认查询过滤器

---

### 10. **Idempotent Design（幂等设计）**

支持安全重试的设计模式。

#### 文档去重
```python
file_sha256: Mapped[str] = mapped_column(
    String(64), nullable=False, unique=True
)
```

#### 分块去重
```python
text_sha256: Mapped[str] = mapped_column(
    String(64), nullable=False
)
```

#### 任务重试
```python
class JobModel:
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
```

**优点**：
- 操作可重复执行
- 避免重复处理
- 支持断点续传

---

## 📊 核心模型详解

### 数据层次结构

```
User (用户)
  ↓
Workspace (工作空间) ← 多租户边界
  ↓
Document (文档)
  ├── Chunks (分块) → 用于 RAG 检索
  ├── Notes (笔记) → 用户知识输出
  │     └── Anchors (锚点) → 链接笔记和原文
  └── Jobs (处理任务) → 异步任务队列

ChatSession (会话)
  └── Messages (消息) → 对话历史 + 引用
```

---

### 1. **UserModel - 用户模型**

**职责**：身份认证、权限管理、多租户隔离

**设计特点**：
- `username` 和 `email` 都是唯一标识
- `is_active` 实现软删除
- `is_superuser` 实现简单 RBAC
- 作为所有资源的所有者（owner）

**关系**：
- `1:N` → Workspaces（拥有多个工作空间）
- `1:N` → Documents（拥有多个文档）
- `1:N` → Notes（拥有多条笔记）
- `1:N` → Sessions（拥有多个会话）

---

### 2. **WorkspaceModel - 工作空间模型**

**职责**：多租户数据隔离、团队协作边界

**设计特点**：
- 所有业务数据都属于某个 workspace
- 权限控制的第一层
- 未来可扩展为团队共享

**关系**：
- `N:1` → User（属于某个用户）
- `1:N` → Documents
- `1:N` → Notes
- `1:N` → Sessions
- `1:N` → Jobs

**未来扩展**：
```python
# 团队成员表（待实现）
class WorkspaceMember:
    workspace_id: int
    user_id: int
    role: str  # owner, admin, member, viewer
```

---

### 3. **DocsModel - 文档模型**

**职责**：PDF 文档元数据管理

**核心字段**：
- **去重标识**：`file_sha256`（全局唯一）
- **状态机**：`status`（UPLOADED → PROCESSING → PROCESSED/ERROR）
- **版本控制**：`chunker_version`, `embed_model`, `embed_dim`

**关系**：
- `N:1` → User（owner）
- `N:1` → Workspace
- `1:N` → Chunks（一对多分块）
- `1:N` → Notes（关联的笔记）
- `1:N` → Anchors（被引用的位置）
- `1:N` → Jobs（处理任务）

**为什么需要版本字段？**
- 分块算法升级时，可以重新处理旧文档
- 嵌入模型更换时，触发重新索引
- 支持 A/B 测试不同的分块策略

---

### 4. **ChunksModel - 分块模型**

**职责**：RAG 检索的基本单位

**核心字段**：
- **顺序保证**：`chunk_index`（保证分块顺序，用于重建文档）
- **去重标识**：`text_sha256`（避免重复计算嵌入）
- **位置信息**：`page_start`, `page_end`, `offsets`, `bboxes`
- **文本内容**：`text`（不存嵌入向量，嵌入存 Neo4j）

**关系**：
- `N:1` → Document
- `1:N` → Anchors（被笔记引用）

**设计权衡**：
- ✅ **Postgres 存文本**：便于全文搜索、审计
- ✅ **Neo4j 存向量**：专业向量检索性能
- ✅ **可重建**：从 Postgres 随时重建 Neo4j 索引

---

### 5. **NoteModel - 笔记模型**

**职责**：用户知识输出，Markdown 笔记

**核心字段**：
- **内容**：`markdown`（支持富文本、公式、代码块）
- **版本**：`version`（未来支持版本控制和协作）

**关系**：
- `N:1` → User（owner）
- `N:1` → Workspace
- `N:1` → Document（关联的文档）
- `1:N` → Anchors（笔记中的引用锚点）

**未来扩展**：
- 笔记也可以被向量化，成为二次检索源
- 支持笔记间的链接（类似 Obsidian）

---

### 6. **AnchorModel - 锚点模型**

**职责**：连接笔记和文档的精确位置

**核心字段**：
- **引用文本**：`quoted_text`（用户选中的原文片段）
- **精确定位**：`locator`（bbox/offset，用于 PDF 高亮和跳转）
- **页码**：`page`（快速定位）

**关系**：
- `N:1` → Note
- `N:1` → Document
- `N:1` → Chunk

**使用场景**：
1. 用户在 PDF 中选中文字，插入笔记
2. 系统创建 Anchor，记录位置
3. 点击笔记中的引用，跳转到 PDF 精确位置并高亮

---

### 7. **ChatSessionModel + MessageModel - 会话模型**

**职责**：管理用户与 AI 的对话

#### ChatSessionModel
- 会话级别的容器
- 只有 `created_at`（会话不可编辑）

#### MessageModel
- **角色**：`role`（user, assistant, system, tool）
- **内容**：`content`
- **引用**：`citation`（答案来源）
- **上下文**：`context`（RAG 检索结果）

**设计要点**：
- `sender_user_id` 可为空（AI/系统消息）
- `citation` 存储引用信息，用于显示来源
- `context` 存储完整检索上下文，用于调试和审计

**引用格式示例**：
```json
{
  "citations": [
    {
      "doc_id": 1,
      "chunk_id": 42,
      "page": 10,
      "quote": "机器学习是人工智能的一个分支...",
      "relevance_score": 0.92
    }
  ]
}
```

---

### 8. **JobModel - 异步任务模型**

**职责**：管理文档处理的后台任务

**核心字段**：
- **任务类型**：`job_type`（INGEST, REINDEX, DELETE）
- **状态**：`status`（PENDING → IN_PROGRESS → COMPLETED/FAILED）
- **重试**：`attempt` / `max_attempt`
- **参数**：`payload`（任务特定参数）
- **进度**：`progress`（0-100）

**任务流程**：
```
1. API 创建 Job（status=PENDING）
2. Worker 拉取 Job（status=IN_PROGRESS）
3. Worker 执行任务，更新 progress
4. 完成或失败（status=COMPLETED/FAILED）
5. 失败时重试（attempt < max_attempt）
```

**关系**：
- `N:1` → Document
- `N:1` → Workspace

---

## 🔗 关系图

### ER 图（简化版）

```
┌─────────────┐
│   User      │
│  (用户)      │
└──────┬──────┘
       │ 1:N
       ↓
┌─────────────┐      1:N      ┌─────────────┐
│ Workspace   │───────────────→│  Document   │
│ (工作空间)   │                │  (文档)      │
└─────────────┘                └──────┬──────┘
                                      │ 1:N
                        ┌─────────────┼─────────────┐
                        ↓             ↓             ↓
                 ┌──────────┐  ┌──────────┐  ┌──────────┐
                 │  Chunk   │  │   Note   │  │   Job    │
                 │ (分块)    │  │  (笔记)   │  │ (任务)   │
                 └────┬─────┘  └────┬─────┘  └──────────┘
                      │             │
                      │    N:N      │
                      └─────────────┘
                            ↓
                      ┌──────────┐
                      │  Anchor  │
                      │ (锚点)    │
                      └──────────┘
```

### 级联删除链

```
User 删除
  ↓ cascade
Workspace 删除
  ↓ cascade
  ├─ Documents 删除
  │    ↓ cascade
  │    ├─ Chunks 删除
  │    ├─ Notes 删除
  │    │    ↓ cascade
  │    │    └─ Anchors 删除
  │    └─ Jobs 删除
  ├─ Sessions 删除
  │    ↓ cascade
  │    └─ Messages 删除
  └─ Notes 删除
```

---

## ✅ 最佳实践

### 1. **查询优化**

#### 使用 `selectinload` 避免 N+1 查询
```python
from sqlalchemy.orm import selectinload

# ❌ N+1 查询
users = session.query(UserModel).all()
for user in users:
    print(user.documents)  # 每次都查询一次

# ✅ 预加载
users = session.query(UserModel).options(
    selectinload(UserModel.documents)
).all()
```

#### 使用 `joinedload` 加载关联数据
```python
from sqlalchemy.orm import joinedload

# 一次查询加载 document + chunks
doc = session.query(DocsModel).options(
    joinedload(DocsModel.chunks)
).first()
```

---

### 2. **事务管理**

```python
async with session.begin():
    # 所有操作在同一事务中
    doc = DocsModel(filename="test.pdf", ...)
    session.add(doc)
    
    chunk = ChunksModel(doc_id=doc.doc_id, ...)
    session.add(chunk)
    
    # 提交或回滚
```

---

### 3. **批量插入**

```python
# ✅ 批量插入
chunks = [
    ChunksModel(doc_id=1, text=f"chunk {i}")
    for i in range(1000)
]
session.add_all(chunks)
await session.commit()
```

---

### 4. **索引使用**

```python
# ✅ 利用复合索引
doc = session.query(DocsModel).filter_by(
    workspace_id=1,  # 索引第一列
    file_sha256="abc123"  # 索引第二列
).first()
```

---

### 5. **JSONB 查询**

```python
# 查询 JSONB 字段
from sqlalchemy import cast, String

# 提取 JSONB 值
messages = session.query(MessageModel).filter(
    MessageModel.citation['doc_id'].astext.cast(Integer) == 1
).all()
```

---

## 🚀 未来扩展方向

### 1. **GraphRAG 支持**
- 在 Neo4j 中添加 Chunk 之间的边（引用、相似、因果）
- 支持图遍历查询

### 2. **多用户协作**
- WorkspaceMember 表
- 细粒度权限控制（RBAC）

### 3. **版本控制**
- Note 的历史版本
- Document 的修订记录

### 4. **全文搜索**
- 使用 PostgreSQL 的 `tsvector`
- 或集成 Elasticsearch

### 5. **审计日志**
- 所有操作记录（谁、何时、做了什么）
- 用于合规和调试

---

## 📚 参考资源

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [PostgreSQL JSONB](https://www.postgresql.org/docs/current/datatype-json.html)
- [Neo4j Vector Search](https://neo4j.com/docs/cypher-manual/current/indexes-for-vector-search/)
