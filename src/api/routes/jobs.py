"""ジョブ管理APIルーター

ジョブの一覧取得・詳細取得・ステータス更新を提供する。
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import JobListResponse, JobResponse, MessageResponse
from src.db.schema import JobCRUD, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"], redirect_slashes=False)

# DBセッション依存性注入型エイリアス
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=JobListResponse)
@router.get("/", response_model=JobListResponse, include_in_schema=False)
async def list_jobs(
    session: DBSession,
    limit: int = 50,
    offset: int = 0,
) -> JobListResponse:
    """ジョブ一覧を取得する"""
    jobs = await JobCRUD.list_all(session, limit=limit, offset=offset)
    return JobListResponse(jobs=jobs, total=len(jobs))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, session: DBSession) -> JobResponse:
    """ジョブ詳細を取得する"""
    job = await JobCRUD.get_by_id(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"ジョブが見つかりません: id={job_id}")
    return job
