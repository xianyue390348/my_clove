from fastapi import APIRouter
from app.api.routes import (
    claude,
    claude_extra,
    accounts,
    settings,
    statistics,
    proxies,
    conversation_logs,
)

api_router = APIRouter()

api_router.include_router(claude.router, prefix="/v1", tags=["Claude API"])
api_router.include_router(
    claude_extra.router, prefix="/v1", tags=["Claude Extra API"]
)
api_router.include_router(
    claude_extra.router, prefix="/api/v1", tags=["Claude Extra API (API prefix)"]
)
api_router.include_router(
    accounts.router, prefix="/api/admin/accounts", tags=["Account Management"]
)
api_router.include_router(
    settings.router, prefix="/api/admin/settings", tags=["Settings Management"]
)
api_router.include_router(
    statistics.router, prefix="/api/admin/statistics", tags=["Statistics"]
)
api_router.include_router(
    proxies.router, prefix="/api/admin/proxies", tags=["Proxy Pool Management"]
)
api_router.include_router(
    conversation_logs.router,
    prefix="/api/admin/conversation-logs",
    tags=["Conversation Logs"],
)
