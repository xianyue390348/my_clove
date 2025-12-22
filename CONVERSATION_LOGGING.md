# 对话日志记录功能

## 功能说明

记录每次 API 对话的完整流程（HTTP → Claude Web API），方便排查问题和调试。

## 存储格式

**JSONL 格式**（每行一个 JSON 对象）：
```
{DATA_FOLDER}/logs/conversations/
  ├── 2025-12-22.jsonl
  ├── 2025-12-23.jsonl
  └── ...
```

每个日志文件包含当天的所有对话记录，每行一条。

## 配置项

### 环境变量

```bash
# 启用/禁用对话日志（默认: true）
ENABLE_CONVERSATION_LOGGING=true

# 日志目录（默认: {DATA_FOLDER}/logs/conversations）
CONVERSATION_LOG_DIR=/custom/path/to/logs

# 日志保留天数（默认: 30）
CONVERSATION_LOG_RETENTION_DAYS=30
```

### .env 文件示例

```env
# 对话日志配置
ENABLE_CONVERSATION_LOGGING=true
CONVERSATION_LOG_RETENTION_DAYS=7
```

## 日志内容

每条日志记录包含：

### 1. 基础元数据
```json
{
  "log_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-12-22T13:24:46.789Z",
  "session_id": "session_1703257486789",
  "conversation_id": "conv-abc123xyz",
  "account_id": "org-uuid-123",
  "duration_ms": 1234,
  "status": "success",
  "is_streaming": true
}
```

### 2. 客户端请求（已脱敏）
```json
{
  "client_request": {
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 4096,
    "stream": true,
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Hello"},
          {
            "type": "image",
            "source": {
              "type": "base64",
              "media_type": "image/png",
              "data": "<base64_data_12345_bytes>"
            }
          }
        ]
      }
    ],
    "system": "You are a helpful assistant"
  }
}
```

> **注意**: 图片的 base64 数据会被替换为 `<base64_data_{length}_bytes>`，避免日志文件过大。

### 3. Claude Web 请求
```json
{
  "claude_web_request": {
    "prompt": "",
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens_to_sample": 4096,
    "attachments": [
      {
        "extracted_content": "Hello",
        "file_name": "paste.txt"
      }
    ],
    "files": ["file-abc123"],
    "rendering_mode": "messages",
    "timezone": "UTC"
  }
}
```

### 4. 收集的完整消息
```json
{
  "collected_message": {
    "id": "msg_01ABC123",
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "Hello! How can I help you today?"
      }
    ],
    "model": "claude-3-5-sonnet-20241022",
    "stop_reason": "end_turn",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 18
    }
  }
}
```

### 5. 错误信息（如果有）
```json
{
  "error": {
    "type": "ConnectionError",
    "message": "Failed to connect to Claude.ai: Connection timeout"
  }
}
```

## 完整示例

### 成功对话
```json
{"log_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","timestamp":"2025-12-22T13:24:46.789Z","session_id":"session_1703257486789","conversation_id":"conv-abc123","account_id":"org-uuid-123","duration_ms":1234,"status":"success","is_streaming":true,"client_request":{"model":"claude-3-5-sonnet-20241022","max_tokens":4096,"messages":[{"role":"user","content":"Hello"}]},"claude_web_request":{"model":"claude-3-5-sonnet-20241022","attachments":[{"extracted_content":"Hello","file_name":"paste.txt"}]},"collected_message":{"id":"msg_01ABC","role":"assistant","content":[{"type":"text","text":"Hello! How can I help?"}],"stop_reason":"end_turn","usage":{"input_tokens":10,"output_tokens":15}}}
```

### 错误对话
```json
{"log_id":"x9y8z7w6-v5u4-3210-dcba-fe9876543210","timestamp":"2025-12-22T13:30:15.123Z","session_id":"session_1703257815123","conversation_id":null,"account_id":"org-uuid-123","duration_ms":5678,"status":"error","is_streaming":true,"client_request":{"model":"claude-3-5-sonnet-20241022","messages":[...]},"claude_web_request":{...},"error":{"type":"ConnectionError","message":"Failed to connect to Claude.ai"}}
```

## 查询日志

### 使用命令行工具

```bash
# 查看最新的 10 条日志
tail -n 10 ~/.clove/data/logs/conversations/$(date +%Y-%m-%d).jsonl

# 格式化显示单条日志
cat ~/.clove/data/logs/conversations/2025-12-22.jsonl | head -1 | jq .

# 筛选错误日志
cat ~/.clove/data/logs/conversations/2025-12-22.jsonl | jq 'select(.status=="error")'

# 筛选特定 session 的日志
cat ~/.clove/data/logs/conversations/2025-12-22.jsonl | jq 'select(.session_id=="session_123")'

# 统计今天的对话数量
cat ~/.clove/data/logs/conversations/$(date +%Y-%m-%d).jsonl | wc -l

# 统计成功和失败的对话数
cat ~/.clove/data/logs/conversations/2025-12-22.jsonl | jq -r '.status' | sort | uniq -c
```

### 使用 Python 脚本

```python
import json
from pathlib import Path
from datetime import datetime

# 读取今天的日志
log_file = Path.home() / ".clove" / "data" / "logs" / "conversations" / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

with open(log_file, "r", encoding="utf-8") as f:
    for line in f:
        log = json.loads(line)
        print(f"[{log['timestamp']}] {log['status']} - {log.get('session_id')}")
        
        # 打印错误信息
        if log['status'] == 'error':
            print(f"  Error: {log['error']['message']}")
```

## 日志维护

### 自动清理

系统会**每天自动清理**超过保留期限的日志文件：
- 默认保留 **30 天**
- 每天自动执行一次清理
- 清理时间：后台定时任务

### 手动清理

如果需要立即清理过期日志，可以重启服务：
```bash
# Docker
docker-compose restart

# 本地运行
# 停止服务后重新启动
```

### 磁盘空间估算

**单条日志大小**：约 1-3 KB（不包含图片数据）

**日均对话量** | **日志大小** | **30天总大小**
---|---|---
100 次 | ~200 KB | ~6 MB
1000 次 | ~2 MB | ~60 MB
10000 次 | ~20 MB | ~600 MB

## 隐私和安全

### 已脱敏内容
- ✅ 图片 base64 数据（替换为长度信息）
- ✅ 文档 base64 数据（替换为长度信息）

### 保留内容
- ✅ 文本消息内容（用于调试）
- ✅ Session ID / Conversation ID（用于关联）
- ✅ 账户 UUID（用于追踪）
- ✅ 模型和参数信息

### 访问控制建议
- 限制日志目录的访问权限
- 定期审查日志内容
- 不要在日志中记录敏感的用户信息

## 禁用日志

如果不需要对话日志功能：

```bash
# 设置环境变量
ENABLE_CONVERSATION_LOGGING=false
```

或在 `.env` 文件中：
```env
ENABLE_CONVERSATION_LOGGING=false
```

重启服务后生效。

## 常见问题

### Q: 日志文件太大怎么办？

**A**: 可以缩短保留天数或手动压缩旧日志：

```bash
# 压缩 7 天前的日志
find ~/.clove/data/logs/conversations -name "*.jsonl" -mtime +7 -exec gzip {} \;
```

### Q: 如何导出特定时间段的日志？

**A**: 使用脚本合并多个文件：

```bash
# 导出 12月22日 到 12月25日 的日志
cat ~/.clove/data/logs/conversations/2025-12-{22,23,24,25}.jsonl > exported_logs.jsonl
```

### Q: 日志记录会影响性能吗？

**A**: 影响极小：
- 使用异步写入，不阻塞主流程
- 只在请求结束时记录一次
- 典型延迟 < 10ms

### Q: 如何查看流式响应的详细过程？

**A**: 流式响应的 SSE 事件不会完整记录（数据量太大），只记录：
- 最终的 `collected_message`（完整消息）
- 处理耗时
- 错误信息（如果有）

## 技术实现

### 架构
```
客户端请求
    ↓
[Pipeline 处理器]
    ├─ ClaudeWebProcessor (构建请求)
    ├─ EventParsingProcessor (解析响应)
    ├─ MessageCollectorProcessor (收集消息)
    └─ ConversationLoggingProcessor ✅ 记录完整流程
    ↓
返回响应
```

### 核心文件
- `app/services/conversation_logger.py` - 日志服务
- `app/processors/claude_ai/conversation_logging_processor.py` - 日志处理器
- `app/core/config.py` - 配置项

### 定时任务
```python
# 每天自动执行一次清理
asyncio.create_task(conversation_logger._cleanup_loop())
```

## 后续扩展（可选）

### 1. Web 查询界面
在管理后台添加日志查看页面：
- 列表展示所有对话
- 按时间、session、状态筛选
- 点击查看详细信息

### 2. 数据库存储
如果需要复杂查询，可以切换到 SQLite：
- 支持索引和全文搜索
- 更方便的统计分析
- 事务支持

### 3. 导出功能
添加日志导出 API：
- CSV 格式导出
- Excel 格式导出
- 按条件批量导出

## 联系和反馈

如有问题或建议，请查看项目文档或提交 Issue。
