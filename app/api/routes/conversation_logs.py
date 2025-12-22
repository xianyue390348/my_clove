from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.dependencies.auth import AdminAuthDep
from app.services.conversation_logger import get_conversation_logger


class ConversationLogResponse(BaseModel):
    """对话日志响应"""

    log_id: str
    timestamp: str
    session_id: Optional[str]
    conversation_id: Optional[str]
    account_id: Optional[str]
    duration_ms: int
    status: str
    is_streaming: bool
    client_request: Optional[dict] = None
    claude_web_request: Optional[dict] = None
    collected_message: Optional[dict] = None
    error: Optional[dict] = None


class ConversationLogsListResponse(BaseModel):
    """对话日志列表响应"""

    total: int
    logs: List[ConversationLogResponse]


router = APIRouter()


@router.get("", response_model=ConversationLogsListResponse)
async def get_conversation_logs(
    _: AdminAuthDep,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    status: Optional[str] = Query(None, description="Filter by status (success/error)"),
    limit: int = Query(100, le=1000, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
):
    """
    查询对话日志列表

    需要管理员权限。支持按日期、session_id、状态筛选。
    """
    conversation_logger = get_conversation_logger()
    if not conversation_logger:
        raise HTTPException(status_code=503, detail="Conversation logger not initialized")

    logs = await conversation_logger.query_logs(
        start_date=start_date,
        end_date=end_date,
        session_id=session_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return ConversationLogsListResponse(total=len(logs), logs=logs)


@router.get("/{log_id}", response_model=ConversationLogResponse)
async def get_conversation_log(log_id: str, _: AdminAuthDep):
    """
    获取单条对话日志详情

    需要管理员权限。
    """
    conversation_logger = get_conversation_logger()
    if not conversation_logger:
        raise HTTPException(status_code=503, detail="Conversation logger not initialized")

    log = await conversation_logger.get_log_by_id(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return ConversationLogResponse(**log)


@router.delete("")
async def cleanup_old_logs(_: AdminAuthDep):
    """
    清理过期的对话日志

    需要管理员权限。
    """
    conversation_logger = get_conversation_logger()
    if not conversation_logger:
        raise HTTPException(status_code=503, detail="Conversation logger not initialized")

    deleted_count = await conversation_logger.cleanup_old_logs()

    return {"deleted_files": deleted_count, "message": f"Cleaned up {deleted_count} old log files"}
