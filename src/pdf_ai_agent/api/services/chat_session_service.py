"""
Chat session service for creating chat sessions.
"""

import logging
import base64
import json
import hashlib
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional, Tuple, List
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from pdf_ai_agent.api.utilties.workspace_utils import check_workspace_membership
from pdf_ai_agent.config.database.models.model_document import (
    AnchorModel,
    ChatSessionModel,
    ChatSessionModeEnum,
    DocsModel,
    NoteModel,
    MessageModel,
    RoleEnum,
)
from pdf_ai_agent.config.database.models.model_user import WorkspaceModel

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "New chat"
ALLOWED_MODELS = {"gpt-4.1-mini"}

DEFAULT_RETRIEVAL: Dict[str, Any] = {
    "enabled": True,
    "top_k": 8,
    "rerank": False,
}

DEFAULT_DEFAULTS: Dict[str, Any] = {
    "model": "gpt-4.1-mini",
    "temperature": 0.2,
    "top_p": 1.0,
    "system_prompt": None,
    "retrieval": DEFAULT_RETRIEVAL,
}
DEFAULT_CONTEXT: Dict[str, Any] = {
    "note_id": None,
    "anchor_ids": [],
    "doc_id": None,
    "doc_anchor_ids": [],
}


class ChatSessionService:
    """Service for chat session operations."""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def _get_workspace(self, workspace_id: int) -> Optional[WorkspaceModel]:
        query = select(WorkspaceModel).where(WorkspaceModel.workspace_id == workspace_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _get_note(self, note_id: int) -> Optional[NoteModel]:
        query = select(NoteModel).where(NoteModel.note_id == note_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _get_doc(self, doc_id: int) -> Optional[DocsModel]:
        query = select(DocsModel).where(DocsModel.doc_id == doc_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _load_anchors(self, anchor_ids: Iterable[int]) -> Dict[int, AnchorModel]:
        anchor_list = list({int(anchor_id) for anchor_id in anchor_ids})
        if not anchor_list:
            return {}
        query = select(AnchorModel).where(AnchorModel.anchor_id.in_(anchor_list))
        result = await self.db_session.execute(query)
        anchors = result.scalars().all()
        if len(anchors) != len(anchor_list):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ANCHOR_INVALID: One or more anchors not found",
            )
        return {anchor.anchor_id: anchor for anchor in anchors}

    @staticmethod
    def _normalize_title(title: Optional[str]) -> str:
        if not title or not title.strip():
            return DEFAULT_TITLE
        return title.strip()[:255]

    @staticmethod
    def _validate_mode(mode: Optional[str]) -> str:
        if mode is None:
            return ChatSessionModeEnum.ASK.value
        if mode not in {e.value for e in ChatSessionModeEnum}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: mode must be one of ask|assist|agent",
            )
        return mode

    @staticmethod
    def _validate_float_range(name: str, value: float, min_value: float, max_value: float, inclusive_min: bool, inclusive_max: bool) -> None:
        if inclusive_min:
            too_low = value < min_value
        else:
            too_low = value <= min_value
        if inclusive_max:
            too_high = value > max_value
        else:
            too_high = value >= max_value
        if too_low or too_high:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"INVALID_ARGUMENT: {name} out of range",
            )

    def _normalize_defaults(self, defaults: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = deepcopy(DEFAULT_DEFAULTS)
        if defaults is None:
            return normalized

        if not isinstance(defaults, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: defaults must be an object",
            )

        if "model" in defaults and defaults["model"] is not None:
            model_name = defaults["model"]
            if model_name not in ALLOWED_MODELS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: model not allowed",
                )
            normalized["model"] = model_name

        if "temperature" in defaults and defaults["temperature"] is not None:
            temperature = float(defaults["temperature"])
            self._validate_float_range("temperature", temperature, 0.0, 2.0, True, True)
            normalized["temperature"] = temperature

        if "top_p" in defaults and defaults["top_p"] is not None:
            top_p = float(defaults["top_p"])
            self._validate_float_range("top_p", top_p, 0.0, 1.0, False, True)
            normalized["top_p"] = top_p

        if "system_prompt" in defaults:
            normalized["system_prompt"] = defaults["system_prompt"]

        if "retrieval" in defaults and defaults["retrieval"] is not None:
            retrieval = defaults["retrieval"]
            if not isinstance(retrieval, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: retrieval must be an object",
                )
            if "enabled" in retrieval and retrieval["enabled"] is not None:
                normalized["retrieval"]["enabled"] = bool(retrieval["enabled"])
            if "top_k" in retrieval and retrieval["top_k"] is not None:
                top_k = int(retrieval["top_k"])
                if top_k < 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="INVALID_ARGUMENT: retrieval.top_k must be >= 1",
                    )
                normalized["retrieval"]["top_k"] = top_k
            if "rerank" in retrieval and retrieval["rerank"] is not None:
                normalized["retrieval"]["rerank"] = bool(retrieval["rerank"])

        return normalized

    async def _validate_context(
        self,
        workspace_id: int,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if context is None:
            return deepcopy(DEFAULT_CONTEXT)
        if not isinstance(context, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: context must be an object",
            )

        note_id = context.get("note_id")
        doc_id = context.get("doc_id")
        anchor_ids = context.get("anchor_ids") or []
        doc_anchor_ids = context.get("doc_anchor_ids") or []

        if doc_anchor_ids and doc_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: doc_anchor_ids requires doc_id",
            )

        if anchor_ids and not isinstance(anchor_ids, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: anchor_ids must be a list",
            )
        if doc_anchor_ids and not isinstance(doc_anchor_ids, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: doc_anchor_ids must be a list",
            )

        if note_id is not None:
            note = await self._get_note(int(note_id))
            if note is None or note.workspace_id != workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="NOTE_NOT_FOUND: Note not found",
                )
            if doc_id is not None and note.doc_id is not None and note.doc_id != int(doc_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="NOTE_DOC_MISMATCH: Note does not belong to document",
                )

        if doc_id is not None:
            doc = await self._get_doc(int(doc_id))
            if doc is None or doc.workspace_id != workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="DOC_NOT_FOUND: Document not found",
                )

        anchor_map = await self._load_anchors(anchor_ids)
        for anchor in anchor_map.values():
            if anchor.workspace_id != workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ANCHOR_INVALID: Anchor not in workspace",
                )
            if note_id is not None and anchor.note_id != int(note_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ANCHOR_INVALID: Anchor not associated with note",
                )

        doc_anchor_map = await self._load_anchors(doc_anchor_ids)
        for anchor in doc_anchor_map.values():
            if anchor.workspace_id != workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ANCHOR_INVALID: Anchor not in workspace",
                )
            if doc_id is not None and anchor.doc_id != int(doc_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ANCHOR_INVALID: Anchor not associated with document",
                )

        return {
            "note_id": int(note_id) if note_id is not None else None,
            "anchor_ids": [int(anchor_id) for anchor_id in anchor_ids],
            "doc_id": int(doc_id) if doc_id is not None else None,
            "doc_anchor_ids": [int(anchor_id) for anchor_id in doc_anchor_ids],
        }

    @staticmethod
    def _normalize_input(input_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        if not input_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: input is empty",
            )

        normalized: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for item in input_items:
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: input items must be objects",
                )
            item_type = item.get("type")
            text = item.get("text")
            if item_type != "text":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: input type must be text",
                )
            if text is None or not str(text).strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: input text is empty",
                )
            normalized.append({"type": "text", "text": str(text)})
            text_parts.append(str(text))

        return normalized, "\n".join(text_parts)

    def _apply_overrides(
        self,
        base_defaults: Dict[str, Any],
        overrides: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = deepcopy(base_defaults)
        if overrides is None:
            return normalized

        if not isinstance(overrides, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: overrides must be an object",
            )

        if "model" in overrides and overrides["model"] is not None:
            model_name = overrides["model"]
            if model_name not in ALLOWED_MODELS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: model not allowed",
                )
            normalized["model"] = model_name

        if "temperature" in overrides and overrides["temperature"] is not None:
            temperature = float(overrides["temperature"])
            self._validate_float_range("temperature", temperature, 0.0, 2.0, True, True)
            normalized["temperature"] = temperature

        if "top_p" in overrides and overrides["top_p"] is not None:
            top_p = float(overrides["top_p"])
            self._validate_float_range("top_p", top_p, 0.0, 1.0, False, True)
            normalized["top_p"] = top_p

        if "system_prompt" in overrides:
            normalized["system_prompt"] = overrides["system_prompt"]

        if "retrieval" in overrides and overrides["retrieval"] is not None:
            retrieval = overrides["retrieval"]
            if not isinstance(retrieval, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: retrieval must be an object",
                )
            if "enabled" in retrieval and retrieval["enabled"] is not None:
                normalized["retrieval"]["enabled"] = bool(retrieval["enabled"])
            if "top_k" in retrieval and retrieval["top_k"] is not None:
                top_k = int(retrieval["top_k"])
                if top_k < 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="INVALID_ARGUMENT: retrieval.top_k must be >= 1",
                    )
                normalized["retrieval"]["top_k"] = top_k
            if "rerank" in retrieval and retrieval["rerank"] is not None:
                normalized["retrieval"]["rerank"] = bool(retrieval["rerank"])

        return normalized

    @staticmethod
    def _compute_request_hash(payload: Dict[str, Any]) -> str:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _estimate_usage(prompt_text: str, completion_text: str) -> Dict[str, int]:
        prompt_tokens = len(prompt_text.split())
        completion_tokens = len(completion_text.split())
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    @staticmethod
    def _build_citations(anchors: List[AnchorModel]) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for anchor in anchors:
            citations.append(
                {
                    "anchor_id": anchor.anchor_id,
                    "doc_id": anchor.doc_id,
                    "page": anchor.page,
                    "locator": anchor.locator,
                    "quoted_text": anchor.quoted_text,
                }
            )
        return citations

    async def _get_session_for_user(
        self,
        workspace_id: int,
        session_id: int,
        user_id: int,
    ) -> ChatSessionModel:
        session_query = select(ChatSessionModel).where(
            ChatSessionModel.session_id == session_id,
            ChatSessionModel.workspace_id == workspace_id,
        )
        result = await self.db_session.execute(session_query)
        session_model = result.scalar_one_or_none()
        if session_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SESSION_NOT_FOUND",
            )
        if session_model.owner_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="FORBIDDEN: No permission to access session",
            )
        return session_model

    async def send_ask_message(
        self,
        workspace_id: int,
        session_id: int,
        user_id: int,
        client_request_id: str,
        input_items: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        overrides: Optional[Dict[str, Any]],
    ) -> Tuple[MessageModel, MessageModel]:
        try:
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access workspace",
                )

            session_model = await self._get_session_for_user(workspace_id, session_id, user_id)

            normalized_client_request_id = client_request_id.strip()
            if not normalized_client_request_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: client_request_id is required",
                )

            normalized_input, input_text = self._normalize_input(input_items)

            base_context = session_model.context_json or deepcopy(DEFAULT_CONTEXT)
            normalized_context = (
                await self._validate_context(workspace_id, context)
                if context is not None
                else await self._validate_context(workspace_id, base_context)
            )

            base_defaults = session_model.defaults_json or deepcopy(DEFAULT_DEFAULTS)
            effective_defaults = self._apply_overrides(base_defaults, overrides)

            request_payload = {
                "input": normalized_input,
                "context": normalized_context,
                "overrides": overrides,
            }
            request_hash = self._compute_request_hash(request_payload)

            existing_query = select(MessageModel).where(
                MessageModel.session_id == session_id,
                MessageModel.workspace_id == workspace_id,
                MessageModel.role == RoleEnum.USER.value,
                MessageModel.context["client_request_id"].astext == normalized_client_request_id,
            )
            existing_result = await self.db_session.execute(existing_query)
            existing_user_message = existing_result.scalar_one_or_none()
            if existing_user_message is not None:
                existing_context = existing_user_message.context or {}
                if existing_context.get("request_hash") != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="CLIENT_REQUEST_ID_CONFLICT: client_request_id already used",
                    )
                assistant_query = select(MessageModel).where(
                    MessageModel.session_id == session_id,
                    MessageModel.workspace_id == workspace_id,
                    MessageModel.role == RoleEnum.ASSISTANT.value,
                    MessageModel.context["parent_user_message_id"].astext == str(existing_user_message.message_id),
                )
                assistant_result = await self.db_session.execute(assistant_query)
                existing_assistant = assistant_result.scalar_one_or_none()
                if existing_assistant is not None:
                    return existing_user_message, existing_assistant
                user_message = existing_user_message
                is_new_user_message = False
            else:
                user_message = MessageModel(
                    session_id=session_id,
                    workspace_id=workspace_id,
                    sender_user_id=user_id,
                    content=input_text,
                    role=RoleEnum.USER.value,
                    context={
                        "client_request_id": normalized_client_request_id,
                        "request_hash": request_hash,
                    },
                )
                self.db_session.add(user_message)
                await self.db_session.flush()
                await self.db_session.refresh(user_message)
                is_new_user_message = True

            anchor_ids = normalized_context.get("anchor_ids") or []
            doc_anchor_ids = normalized_context.get("doc_anchor_ids") or []
            anchor_map = await self._load_anchors(list({*anchor_ids, *doc_anchor_ids}))
            citations = self._build_citations(list(anchor_map.values()))

            assistant_text = (
                "MVP response: "
                f"{input_text[:500]}"
                + ("..." if len(input_text) > 500 else "")
            )
            usage = self._estimate_usage(input_text, assistant_text)

            assistant_message = MessageModel(
                session_id=session_id,
                workspace_id=workspace_id,
                sender_user_id=None,
                content=assistant_text,
                role=RoleEnum.ASSISTANT.value,
                citation=citations or None,
                context={
                    "client_request_id": normalized_client_request_id,
                    "parent_user_message_id": user_message.message_id,
                    "model": effective_defaults.get("model"),
                    "usage": usage,
                    "request_hash": request_hash,
                },
            )
            self.db_session.add(assistant_message)
            await self.db_session.flush()
            await self.db_session.refresh(assistant_message)

            session_model.last_message_at = assistant_message.created_at
            increment = 2 if is_new_user_message else 1
            session_model.message_count = (session_model.message_count or 0) + increment
            session_model.updated_at = datetime.now(timezone.utc)
            await self.db_session.commit()

            return user_message, assistant_message

        except HTTPException:
            await self.db_session.rollback()
            raise
        except Exception as exc:
            await self.db_session.rollback()
            logger.error("Send ask message failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="INTERNAL_ERROR: An unexpected error occurred",
            )

    @staticmethod
    def encode_cursor(session_id: int, updated_at: datetime) -> str:
        cursor_data = {"session_id": session_id, "updated_at": updated_at.isoformat()}
        cursor_json = json.dumps(cursor_data, separators=(",", ":"))
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.urlsafe_b64encode(cursor_bytes).decode("utf-8").rstrip("=")
        return encoded

    @staticmethod
    def decode_cursor(cursor: str) -> Tuple[int, datetime]:
        try:
            padding = 4 - (len(cursor) % 4)
            if padding != 4:
                cursor += "=" * padding
            cursor_bytes = base64.urlsafe_b64decode(cursor.encode("utf-8"))
            cursor_json = cursor_bytes.decode("utf-8")
            cursor_data = json.loads(cursor_json)
            if "session_id" not in cursor_data or "updated_at" not in cursor_data:
                raise ValueError("Missing required fields in cursor")
            session_id = int(cursor_data["session_id"])
            updated_at = datetime.fromisoformat(cursor_data["updated_at"])
            return session_id, updated_at
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("Invalid cursor: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_CURSOR",
            )

    @staticmethod
    def _validate_mode_filter(mode: Optional[str]) -> Optional[str]:
        if mode is None:
            return None
        if mode not in {e.value for e in ChatSessionModeEnum}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: mode must be one of ask|assist|agent",
            )
        return mode

    async def list_sessions(
        self,
        workspace_id: int,
        user_id: int,
        mode: Optional[str] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
    ) -> Tuple[List[ChatSessionModel], Optional[str]]:
        try:
            workspace = await self._get_workspace(workspace_id)
            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="WORKSPACE_NOT_FOUND: Workspace not found",
                )

            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access workspace",
                )

            if limit < 1 or limit > 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: limit out of range",
                )

            normalized_mode = self._validate_mode_filter(mode)

            query = select(ChatSessionModel).where(
                ChatSessionModel.workspace_id == workspace_id,
                ChatSessionModel.owner_user_id == user_id,
            )
            if normalized_mode is not None:
                query = query.where(ChatSessionModel.mode == normalized_mode)

            if cursor:
                cursor_session_id, cursor_updated_at = self.decode_cursor(cursor)
                query = query.where(
                    or_(
                        ChatSessionModel.updated_at < cursor_updated_at,
                        and_(
                            ChatSessionModel.updated_at == cursor_updated_at,
                            ChatSessionModel.session_id < cursor_session_id,
                        ),
                    )
                )

            query = query.order_by(
                ChatSessionModel.updated_at.desc(),
                ChatSessionModel.session_id.desc(),
            ).limit(limit + 1)

            result = await self.db_session.execute(query)
            sessions = list(result.scalars().all())

            has_next_page = len(sessions) > limit
            if has_next_page:
                sessions = sessions[:limit]
                last_session = sessions[-1]
                next_cursor = self.encode_cursor(last_session.session_id, last_session.updated_at)
            else:
                next_cursor = None

            return sessions, next_cursor

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("List chat sessions failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DB_QUERY_FAILED",
            )

    @staticmethod
    def encode_message_cursor(message_id: int, created_at: datetime) -> str:
        cursor_data = {"message_id": message_id, "created_at": created_at.isoformat()}
        cursor_json = json.dumps(cursor_data, separators=(",", ":"))
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.urlsafe_b64encode(cursor_bytes).decode("utf-8").rstrip("=")
        return encoded

    @staticmethod
    def decode_message_cursor(cursor: str) -> Tuple[int, datetime]:
        try:
            padding = 4 - (len(cursor) % 4)
            if padding != 4:
                cursor += "=" * padding
            cursor_bytes = base64.urlsafe_b64decode(cursor.encode("utf-8"))
            cursor_json = cursor_bytes.decode("utf-8")
            cursor_data = json.loads(cursor_json)
            if "message_id" not in cursor_data or "created_at" not in cursor_data:
                raise ValueError("Missing required fields in cursor")
            message_id = int(cursor_data["message_id"])
            created_at = datetime.fromisoformat(cursor_data["created_at"])
            return message_id, created_at
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("Invalid message cursor: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_CURSOR",
            )

    @staticmethod
    def _validate_order(order: Optional[str]) -> str:
        if order is None:
            return "desc"
        normalized = order.lower()
        if normalized not in {"asc", "desc"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="INVALID_ARGUMENT: order must be asc or desc",
            )
        return normalized

    async def get_session_messages(
        self,
        workspace_id: int,
        session_id: int,
        user_id: int,
        limit: int = 3,
        cursor: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Tuple[ChatSessionModel, List[MessageModel], Optional[str]]:
        try:
            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access workspace",
                )
            
            session_query = select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.workspace_id == workspace_id,
            )
            result = await self.db_session.execute(session_query)
            session_model = result.scalar_one_or_none()
            if session_model is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="SESSION_NOT_FOUND",
                )

            if session_model.owner_user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access session",
                )

            if limit < 1 or limit > 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="INVALID_ARGUMENT: limit out of range",
                )

            sort_order = self._validate_order(order)

            message_query = select(MessageModel).where(
                MessageModel.session_id == session_id,
                MessageModel.workspace_id == workspace_id,
            )

            if cursor:
                cursor_message_id, cursor_created_at = self.decode_message_cursor(cursor)
                if sort_order == "desc":
                    message_query = message_query.where(
                        or_(
                            MessageModel.created_at < cursor_created_at,
                            and_(
                                MessageModel.created_at == cursor_created_at,
                                MessageModel.message_id < cursor_message_id,
                            ),
                        )
                    )
                else:
                    message_query = message_query.where(
                        or_(
                            MessageModel.created_at > cursor_created_at,
                            and_(
                                MessageModel.created_at == cursor_created_at,
                                MessageModel.message_id > cursor_message_id,
                            ),
                        )
                    )

            if sort_order == "desc":
                message_query = message_query.order_by(
                    MessageModel.created_at.desc(),
                    MessageModel.message_id.desc(),
                )
            else:
                message_query = message_query.order_by(
                    MessageModel.created_at.asc(),
                    MessageModel.message_id.asc(),
                )

            message_query = message_query.limit(limit + 1)
            message_result = await self.db_session.execute(message_query)
            messages = list(message_result.scalars().all())

            has_next_page = len(messages) > limit
            if has_next_page:
                messages = messages[:limit]
                last_message = messages[-1]
                next_cursor = self.encode_message_cursor(last_message.message_id, last_message.created_at)
            else:
                next_cursor = None

            return session_model, messages, next_cursor

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Get chat session failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DB_QUERY_FAILED",
            )

    async def create_session(
        self,
        workspace_id: int,
        user_id: int,
        title: Optional[str],
        mode: Optional[str],
        context: Optional[Dict[str, Any]],
        defaults: Optional[Dict[str, Any]],
        client_request_id: Optional[str],
    ) -> ChatSessionModel:
        try:
            workspace = await self._get_workspace(workspace_id)
            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="WORKSPACE_NOT_FOUND: Workspace not found",
                )

            has_access = await check_workspace_membership(workspace_id, user_id, self.db_session)
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="FORBIDDEN: No permission to access workspace",
                )

            normalized_title = self._normalize_title(title)
            normalized_mode = self._validate_mode(mode)
            normalized_defaults = self._normalize_defaults(defaults)
            normalized_context = await self._validate_context(workspace_id, context)

            normalized_client_request_id = client_request_id.strip() if client_request_id else None
            if normalized_client_request_id:
                existing_query = select(ChatSessionModel).where(
                    ChatSessionModel.workspace_id == workspace_id,
                    ChatSessionModel.client_request_id == normalized_client_request_id,
                )
                result = await self.db_session.execute(existing_query)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    if existing.owner_user_id != user_id:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="CLIENT_REQUEST_ID_CONFLICT: client_request_id already used",
                        )
                    return existing

            session_model = ChatSessionModel(
                workspace_id=workspace_id,
                owner_user_id=user_id,
                title=normalized_title,
                mode=normalized_mode,
                context_json=normalized_context,
                defaults_json=normalized_defaults,
                client_request_id=normalized_client_request_id,
            )

            self.db_session.add(session_model)
            await self.db_session.commit()
            await self.db_session.refresh(session_model)

            logger.info(
                "Chat session created: session_id=%s, workspace_id=%s, user_id=%s",
                session_model.session_id,
                workspace_id,
                user_id,
            )

            return session_model

        except HTTPException:
            await self.db_session.rollback()
            raise
        except Exception as exc:
            await self.db_session.rollback()
            logger.error("Chat session creation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="INTERNAL_ERROR: An unexpected error occurred",
            )
