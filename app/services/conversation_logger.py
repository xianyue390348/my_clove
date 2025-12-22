import json
import uuid
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger


class ConversationLogger:
    """对话日志记录服务"""

    def __init__(self, log_dir: Path, retention_days: int = 30):
        """
        初始化对话日志记录器

        Args:
            log_dir: 日志目录路径
            retention_days: 日志保留天数
        """
        self.log_dir = log_dir
        self.retention_days = retention_days
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 86400  # 每天清理一次（秒）
        logger.info(f"Conversation logger initialized at {self.log_dir}")

    def _get_log_file(self, date: Optional[datetime] = None) -> Path:
        """
        获取指定日期的日志文件路径

        Args:
            date: 日期对象，默认为当天

        Returns:
            日志文件路径
        """
        if date is None:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.jsonl"

    async def log_conversation(self, log_data: Dict[str, Any]) -> str:
        """
        记录一次完整对话

        Args:
            log_data: 对话数据

        Returns:
            log_id: 日志唯一标识
        """
        try:
            # 添加基础元数据
            log_id = str(uuid.uuid4())
            log_data["log_id"] = log_id
            log_data["timestamp"] = datetime.utcnow().isoformat() + "Z"

            # 获取当天的日志文件
            log_file = self._get_log_file()

            # 异步写入日志（追加模式）
            async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
                await f.write(json.dumps(log_data, ensure_ascii=False) + "\n")

            logger.debug(f"Logged conversation: {log_id}")
            return log_id

        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")
            return ""

    async def query_logs(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        查询日志记录

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            session_id: 会话 ID
            status: 状态过滤 (success/error)
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志记录列表
        """
        try:
            # 确定查询的日期范围
            if start_date:
                start = datetime.strptime(start_date, "%Y-%m-%d")
            else:
                start = datetime.now() - timedelta(days=7)

            if end_date:
                end = datetime.strptime(end_date, "%Y-%m-%d")
            else:
                end = datetime.now()

            logs = []
            current_date = start

            # 遍历日期范围内的所有日志文件
            while current_date <= end:
                log_file = self._get_log_file(current_date)

                if log_file.exists():
                    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                        async for line in f:
                            try:
                                log = json.loads(line.strip())

                                # 应用过滤条件
                                if session_id and log.get("session_id") != session_id:
                                    continue
                                if status and log.get("status") != status:
                                    continue

                                logs.append(log)

                            except json.JSONDecodeError:
                                continue

                current_date += timedelta(days=1)

            # 按时间戳倒序排序
            logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            # 应用分页
            return logs[offset : offset + limit]

        except Exception as e:
            logger.error(f"Failed to query logs: {e}")
            return []

    async def get_log_by_id(self, log_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 log_id 获取单条日志

        Args:
            log_id: 日志唯一标识

        Returns:
            日志记录，如果未找到返回 None
        """
        try:
            # 搜索最近 7 天的日志文件
            for i in range(7):
                date = datetime.now() - timedelta(days=i)
                log_file = self._get_log_file(date)

                if log_file.exists():
                    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                        async for line in f:
                            try:
                                log = json.loads(line.strip())
                                if log.get("log_id") == log_id:
                                    return log
                            except json.JSONDecodeError:
                                continue

            return None

        except Exception as e:
            logger.error(f"Failed to get log by id: {e}")
            return None

    async def cleanup_old_logs(self) -> int:
        """
        清理过期的日志文件

        Returns:
            删除的文件数量
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            deleted_count = 0

            for log_file in self.log_dir.glob("*.jsonl"):
                try:
                    # 从文件名解析日期
                    file_date_str = log_file.stem  # 2025-12-22
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d")

                    if file_date < cutoff_date:
                        log_file.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old log file: {log_file}")
                except ValueError:
                    # 文件名格式不符合，跳过
                    continue

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old log files")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0

    async def start_cleanup_task(self):
        """启动定时清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Conversation log cleanup task started")

    async def stop_cleanup_task(self):
        """停止定时清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Conversation log cleanup task stopped")

    async def _cleanup_loop(self):
        """定时清理循环"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")


# 全局单例
_conversation_logger: Optional[ConversationLogger] = None


def init_conversation_logger(log_dir: Path, retention_days: int = 30):
    """初始化全局对话日志记录器"""
    global _conversation_logger
    _conversation_logger = ConversationLogger(log_dir, retention_days)
    logger.info("Global conversation logger initialized")


def get_conversation_logger() -> Optional[ConversationLogger]:
    """获取全局对话日志记录器"""
    return _conversation_logger
