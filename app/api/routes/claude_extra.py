"""
Claude API 额外接口的 Mock 实现

这些接口提供与 Claude 官方 API 兼容的响应格式，但返回的是模拟数据。
主要用于兼容 Claude Code 等客户端的额外功能需求。
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from app.dependencies.auth import AuthDep

router = APIRouter()


@router.get("/usage")
async def get_usage(
    _: AuthDep,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> JSONResponse:
    """
    获取 API 使用统计（Mock 数据）

    返回格式兼容 Claude 官方 API 的 /v1/usage 接口
    """
    return JSONResponse(
        content={
            "data": [
                {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "cache_creation_input_tokens": 200,
                        "cache_read_input_tokens": 100,
                    },
                    "cost": {
                        "input_cost": 0.01,
                        "output_cost": 0.02,
                        "cache_creation_cost": 0.005,
                        "cache_read_cost": 0.001,
                        "total_cost": 0.036,
                    },
                }
            ],
            "summary": {
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cache_creation_tokens": 200,
                "total_cache_read_tokens": 100,
                "total_cost": 0.036,
            },
        }
    )


@router.get("/me")
async def get_me(_: AuthDep) -> JSONResponse:
    """
    获取当前用户信息（Mock 数据）

    Claude Code 客户端需要此接口来验证认证状态
    """
    return JSONResponse(
        content={
            "id": "user_mock_12345",
            "email": "user@example.com",
            "name": "Mock User",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "account_type": "claude_pro",
        }
    )


@router.get("/models")
async def get_models(_: AuthDep) -> JSONResponse:
    """
    获取可用模型列表（Mock 数据）

    返回 Claude 系列模型的列表
    """
    return JSONResponse(
        content={
            "data": [
                {
                    "id": "claude-opus-4-20250514",
                    "name": "Claude Opus 4",
                    "created": 1715644800,
                    "type": "model",
                    "display_name": "Claude Opus 4 (May 2025)",
                    "max_tokens": 4096,
                },
                {
                    "id": "claude-sonnet-4-20250514",
                    "name": "Claude Sonnet 4",
                    "created": 1715644800,
                    "type": "model",
                    "display_name": "Claude Sonnet 4 (May 2025)",
                    "max_tokens": 8192,
                },
                {
                    "id": "claude-sonnet-4-5-20250929",
                    "name": "Claude Sonnet 4.5",
                    "created": 1727568000,
                    "type": "model",
                    "display_name": "Claude Sonnet 4.5 (Sep 2025)",
                    "max_tokens": 8192,
                },
                {
                    "id": "claude-haiku-4-20250514",
                    "name": "Claude Haiku 4",
                    "created": 1715644800,
                    "type": "model",
                    "display_name": "Claude Haiku 4 (May 2025)",
                    "max_tokens": 4096,
                },
                {
                    "id": "claude-3-5-sonnet-20241022",
                    "name": "Claude 3.5 Sonnet",
                    "created": 1729555200,
                    "type": "model",
                    "display_name": "Claude 3.5 Sonnet (Oct 2024)",
                    "max_tokens": 8192,
                },
            ],
            "object": "list",
        }
    )


@router.post("/messages/count_tokens")
async def count_tokens(_: AuthDep) -> JSONResponse:
    """
    计算消息的 token 数量（Mock 数据）

    Claude Beta API 功能，用于预估 token 使用量
    """
    return JSONResponse(
        content={
            "input_tokens": 1000,
        }
    )


@router.get("/key-info")
async def get_key_info(_: AuthDep) -> JSONResponse:
    """
    获取 API Key 信息和配额（Mock 数据）
    """
    return JSONResponse(
        content={
            "api_key_id": "key_mock_67890",
            "name": "Mock API Key",
            "created_at": "2024-01-01T00:00:00.000000Z",
            "rate_limit": {
                "requests_per_minute": 50,
                "tokens_per_minute": 100000,
                "tokens_per_day": 1000000,
            },
            "usage": {
                "requests_today": 10,
                "tokens_today": 5000,
                "requests_this_minute": 2,
                "tokens_this_minute": 1000,
            },
            "quota": {
                "remaining_requests_today": 990,
                "remaining_tokens_today": 995000,
                "remaining_requests_this_minute": 48,
                "remaining_tokens_this_minute": 99000,
            },
        }
    )


@router.get("/organizations/{organization_id}/usage")
async def get_organization_usage(
    _: AuthDep,
    organization_id: str = Path(..., description="组织 ID"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
) -> JSONResponse:
    """
    获取组织级别的使用统计（Mock 数据）
    """
    return JSONResponse(
        content={
            "organization_id": organization_id,
            "data": [
                {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "usage": {
                        "input_tokens": 10000,
                        "output_tokens": 5000,
                        "cache_creation_input_tokens": 2000,
                        "cache_read_input_tokens": 1000,
                    },
                    "cost": {
                        "input_cost": 0.10,
                        "output_cost": 0.20,
                        "cache_creation_cost": 0.05,
                        "cache_read_cost": 0.01,
                        "total_cost": 0.36,
                    },
                    "requests": 100,
                }
            ],
            "summary": {
                "total_input_tokens": 10000,
                "total_output_tokens": 5000,
                "total_cache_creation_tokens": 2000,
                "total_cache_read_tokens": 1000,
                "total_requests": 100,
                "total_cost": 0.36,
            },
        }
    )
