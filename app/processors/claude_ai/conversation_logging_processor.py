import time
from typing import Dict, Any
from loguru import logger

from app.processors.base import BaseProcessor
from app.processors.claude_ai import ClaudeAIContext
from app.services.conversation_logger import get_conversation_logger
from app.core.config import settings


class ConversationLoggingProcessor(BaseProcessor):
    """记录对话流程的处理器"""

    async def process(self, context: ClaudeAIContext) -> ClaudeAIContext:
        """
        在处理流程的最后记录完整对话

        Requires:
            - messages_api_request in context
            - claude_web_request in context (可选)
            - collected_message in context (可选)
            - response in context (可选)

        Produces:
            - 无（仅记录日志到文件）
        """
        # 检查是否启用日志记录
        if not settings.enable_conversation_logging:
            logger.debug("Conversation logging is disabled")
            return context

        # 获取日志记录器
        conversation_logger = get_conversation_logger()
        if not conversation_logger:
            logger.warning("Conversation logger not initialized")
            return context

        # 跳过测试消息
        if context.metadata.get("is_test_message"):
            logger.debug("Skipping test message logging")
            return context

        try:
            # 构建日志数据
            log_data = self._build_log_data(context)

            # 异步记录日志
            await conversation_logger.log_conversation(log_data)

            logger.debug(f"Logged conversation for session: {log_data.get('session_id')}")

        except Exception as e:
            # 日志记录失败不应该影响主流程
            logger.error(f"Failed to log conversation: {e}")

        return context

    def _build_log_data(self, context: ClaudeAIContext) -> Dict[str, Any]:
        """
        构建日志数据

        Args:
            context: 处理上下文

        Returns:
            日志数据字典
        """
        # 计算处理耗时
        start_time = context.metadata.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # 基础元数据
        log_data = {
            "session_id": (
                context.claude_session.session_id if context.claude_session else None
            ),
            "conversation_id": (
                context.claude_session.conversation_id
                if context.claude_session
                else None
            ),
            "account_email": (
                context.claude_session.account.email if context.claude_session else None
            ),
            "duration_ms": duration_ms,
            "status": "success" if context.response else "error",
            "is_streaming": (
                context.messages_api_request.stream
                if context.messages_api_request
                else False
            ),
        }

        # 客户端请求（脱敏处理）
        if context.messages_api_request:
            log_data["client_request"] = self._sanitize_request(
                context.messages_api_request.model_dump(exclude_none=True)
            )

        # Claude Web 请求
        if context.claude_web_request:
            log_data["claude_web_request"] = context.claude_web_request.model_dump(
                exclude_none=True
            )

        # 收集的完整消息
        if context.collected_message:
            log_data["collected_message"] = context.collected_message.model_dump(
                exclude_none=True
            )

        # 错误信息（如果有）
        if hasattr(context, "error") and context.error:
            log_data["error"] = {
                "type": type(context.error).__name__,
                "message": str(context.error),
            }

        return log_data

    def _sanitize_request(self, request_data: dict) -> dict:
        """
        脱敏处理：移除敏感信息

        Args:
            request_data: 原始请求数据

        Returns:
            脱敏后的请求数据
        """
        # 深拷贝避免修改原数据
        import copy

        sanitized = copy.deepcopy(request_data)

        # 处理消息中的图片数据
        if "messages" in sanitized:
            for msg in sanitized["messages"]:
                if isinstance(msg.get("content"), list):
                    for block in msg["content"]:
                        # 移除图片的 base64 数据（太大）
                        if block.get("type") == "image":
                            if "source" in block and "data" in block["source"]:
                                data_len = len(block["source"]["data"])
                                block["source"]["data"] = f"<base64_data_{data_len}_bytes>"

                        # 移除文档的 base64 数据
                        elif block.get("type") == "document":
                            if "source" in block and "data" in block["source"]:
                                data_len = len(block["source"]["data"])
                                block["source"]["data"] = f"<base64_data_{data_len}_bytes>"

        return sanitized
