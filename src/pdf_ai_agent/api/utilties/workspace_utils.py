from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pdf_ai_agent.config.database.models.model_user import WorkspaceModel

async def check_workspace_membership(
        workspace_id: int, user_id: int, session: AsyncSession
    ) -> bool:
        """
        Check if user has access to workspace.

        Args:
            workspace_id: Workspace ID
            user_id: User ID 
        Returns:
            True if user has access, False otherwise 
        """
        query = select(WorkspaceModel).where(
            WorkspaceModel.workspace_id == workspace_id,
            WorkspaceModel.owner_user_id == user_id,
        )
        result = await session.execute(query)
        workspace = result.scalar_one_or_none()

        return workspace is not None