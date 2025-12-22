# 属性参考文档

本文档列出项目中主要类的属性，供开发时参考，避免属性名错误。

## ClaudeWebSession 类

**文件**: `app/core/claude_session.py`

### 初始化属性
```python
self.session_id: str                          # 会话 ID
self.last_activity: datetime                  # 最后活动时间
self.conv_uuid: Optional[str] = None          # 对话 UUID（创建对话后才有）
self.paprika_mode: Optional[str] = None       # 思维模式
self.sse_stream: Optional[AsyncIterator[str]] = None  # SSE 流
```

### 运行时属性（在 initialize() 后）
```python
self.account: Account                         # 关联的账户对象
self.client: ClaudeWebClient                  # Claude Web 客户端
```

### 使用示例
```python
# ✅ 正确
session.session_id
session.conv_uuid
session.account.organization_uuid

# ❌ 错误
session.conversation_id  # 不存在！应该用 conv_uuid
session.account.email    # 不存在！应该用 organization_uuid
```

---

## Account 类

**文件**: `app/core/account.py`

### 属性列表
```python
self.organization_uuid: str                   # 组织 UUID（唯一标识）
self.capabilities: Optional[List[str]]        # 账户能力列表
self.cookie_value: Optional[str]              # Cookie 值
self.status: AccountStatus                    # 账户状态
self.auth_type: AuthType                      # 认证类型
self.last_used: datetime                      # 最后使用时间
self.resets_at: Optional[datetime]            # 限流重置时间
self.oauth_token: Optional[OAuthToken]        # OAuth Token
```

### 计算属性
```python
@property
self.is_pro: bool                             # 是否为 Pro 账户
self.is_max: bool                             # 是否为 Max 账户
self.has_oauth: bool                          # 是否有 OAuth Token
```

### 使用示例
```python
# ✅ 正确
account.organization_uuid
account.status
account.is_pro

# ❌ 错误
account.email            # 不存在！应该用 organization_uuid
account.uuid             # 不存在！应该用 organization_uuid
account.id               # 不存在！应该用 organization_uuid
```

---

## ClaudeAIContext 类

**文件**: `app/processors/claude_ai/context.py`

### 属性列表
```python
self.original_request: Request                              # 原始 FastAPI Request
self.messages_api_request: Optional[MessagesAPIRequest]     # 客户端 API 请求
self.claude_web_request: Optional[ClaudeWebRequest]         # Claude Web 请求
self.claude_session: Optional[ClaudeWebSession]             # Claude 会话
self.original_stream: Optional[AsyncIterator[str]]          # 原始 SSE 流
self.event_stream: Optional[AsyncIterator[StreamingEvent]]  # 解析后的事件流
self.collected_message: Optional[Message]                   # 收集的完整消息
self.response: Optional[StreamingResponse | JSONResponse]   # 最终响应
self.metadata: dict                                         # 元数据字典
```

### 使用示例
```python
# ✅ 正确
context.claude_session.session_id
context.claude_session.conv_uuid
context.messages_api_request.stream
context.metadata.get("start_time")

# ❌ 错误
context.session_id       # 不存在！应该用 claude_session.session_id
```

---

## 对话日志记录的字段映射

### 日志字段 → 源属性

| 日志字段 | 源属性路径 | 说明 |
|---------|-----------|------|
| `log_id` | 自动生成 | UUID |
| `timestamp` | 自动生成 | ISO 8601 格式 |
| `session_id` | `context.claude_session.session_id` | 会话 ID |
| `conversation_id` | `context.claude_session.conv_uuid` | 对话 UUID |
| `account_id` | `context.claude_session.account.organization_uuid` | 账户 UUID |
| `duration_ms` | `time.time() - metadata["start_time"]` | 处理耗时（毫秒） |
| `status` | `"success" if context.response else "error"` | 状态 |
| `is_streaming` | `context.messages_api_request.stream` | 是否流式 |
| `client_request` | `context.messages_api_request.model_dump()` | 客户端请求 |
| `claude_web_request` | `context.claude_web_request.model_dump()` | Web 请求 |
| `collected_message` | `context.collected_message.model_dump()` | 完整消息 |
| `error` | `context.error` | 错误信息 |

---

## 常见错误和修复

### 错误 1: 'ClaudeWebSession' object has no attribute 'conversation_id'
```python
# ❌ 错误
context.claude_session.conversation_id

# ✅ 正确
context.claude_session.conv_uuid
```

### 错误 2: 'Account' object has no attribute 'email'
```python
# ❌ 错误
context.claude_session.account.email

# ✅ 正确
context.claude_session.account.organization_uuid
```

### 错误 3: 'ClaudeWebSession' object has no attribute 'account'
```python
# ❌ 错误（session 可能未初始化）
context.claude_session.account.organization_uuid

# ✅ 正确（安全访问）
if hasattr(context.claude_session, "account") and context.claude_session.account:
    org_uuid = context.claude_session.account.organization_uuid

# 或者使用 getattr
org_uuid = getattr(
    getattr(context.claude_session, "account", None),
    "organization_uuid",
    None
)
```

---

## 开发建议

### 1. 使用 getattr() 进行安全访问

```python
# 推荐方式
value = getattr(obj, "attribute_name", default_value)

# 而不是
value = obj.attribute_name if hasattr(obj, "attribute_name") else default_value
```

### 2. 多层属性访问要逐层检查

```python
# ❌ 不安全
account_id = context.claude_session.account.organization_uuid

# ✅ 安全
account_id = None
if context.claude_session:
    if hasattr(context.claude_session, "account"):
        account = context.claude_session.account
        if account:
            account_id = getattr(account, "organization_uuid", None)
```

### 3. 使用 try-except 作为最后防线

```python
try:
    account_id = context.claude_session.account.organization_uuid
except (AttributeError, TypeError) as e:
    logger.warning(f"Failed to get account_id: {e}")
    account_id = None
```

---

## 更新记录

- **2025-12-22**: 初始版本，记录主要类的属性
- 修复了 `conversation_id` → `conv_uuid` 的错误
- 修复了 `account.email` → `account.organization_uuid` 的错误
- 添加了安全访问模式

---

## 维护提示

**⚠️ 重要**: 当添加新的属性访问时，请：

1. 先查阅本文档确认属性名
2. 使用安全的访问方式（`getattr` 或 `hasattr` + try-except）
3. 更新本文档（如果添加了新属性）
4. 在相关的处理器中添加注释说明属性来源

**📝 文档更新**: 如果修改了类的属性，请同步更新本文档！
