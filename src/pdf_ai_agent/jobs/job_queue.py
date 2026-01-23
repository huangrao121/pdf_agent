"""
Simple job queue service for background tasks.

For MVP, this is a simple in-memory queue. In production, this would
be replaced with a proper job queue system like Celery, RQ, or cloud-based solutions.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pdf_ai_agent.config.database.models.model_document import (
    JobModel,
    JobTypeEnum,
    JobStatusEnum,
)

logger = logging.getLogger(__name__)


class JobQueueService:
    """
    Simple job queue service.
    
    For MVP, this creates job records in the database that can be
    picked up by workers. In production, integrate with a proper
    job queue system.
    """
    
    async def enqueue_job(
        self,
        session: AsyncSession,
        job_type: JobTypeEnum,
        doc_id: int,
        workspace_id: int,
        payload: Optional[Dict[str, Any]] = None,
        max_attempt: int = 3
    ) -> JobModel:
        """
        Enqueue a new job.
        
        Args:
            session: Database session
            job_type: Type of job
            doc_id: Document ID
            workspace_id: Workspace ID
            payload: Optional job-specific payload
            max_attempt: Maximum retry attempts
        
        Returns:
            Created JobModel
        
        Raises:
            Exception: If job creation fails
        """
        try:
            job = JobModel(
                doc_id=doc_id,
                workspace_id=workspace_id,
                job_type=job_type,
                status=JobStatusEnum.PENDING,
                payload=payload or {},
                attempt=0,
                max_attempt=max_attempt,
                progress=0.0,
            )
            
            session.add(job)
            await session.commit()
            await session.refresh(job)
            
            logger.info(
                f"Enqueued job {job.job_id}: {job_type.value} for doc_id={doc_id}"
            )
            
            return job
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to enqueue job: {e}")
            raise
    
    async def get_pending_jobs(
        self,
        session: AsyncSession,
        job_type: Optional[JobTypeEnum] = None,
        limit: int = 10
    ) -> list[JobModel]:
        """
        Get pending jobs from the queue.
        
        Args:
            session: Database session
            job_type: Optional filter by job type
            limit: Maximum number of jobs to return
        
        Returns:
            List of pending JobModel instances
        """
        query = select(JobModel).where(
            JobModel.status == JobStatusEnum.PENDING
        )
        
        if job_type:
            query = query.where(JobModel.job_type == job_type)
        
        query = query.limit(limit)
        
        result = await session.execute(query)
        return list(result.scalars().all())


# Global job queue service instance
_job_queue_service: JobQueueService = None


def get_job_queue_service() -> JobQueueService:
    """
    Get or create job queue service instance.
    
    Returns:
        JobQueueService instance
    """
    global _job_queue_service
    if _job_queue_service is None:
        _job_queue_service = JobQueueService()
    return _job_queue_service
