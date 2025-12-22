# 请求处理流程

本文档详细说明从客户端请求到返回响应的完整处理流程。

**注意**: 本项目仅使用 **Web 反向代理模式** (claude-web-api)，不使用 OAuth API 模式。

## 流程概览

```
客户端请求
    ↓
[1] FastAPI 路由入口 (app/api/routes/claude.py)
    ↓
[2] 创建 ClaudeAIContext 上下文对象
    ↓
[3] ClaudeAIPipeline 处理器管道
    ↓
    ├─→ [3.1] TestMessageProcessor - 测试消息处理
    ├─→ [3.2] ToolResultProcessor - 工具结果处理
    ├─→ [3.3] ClaudeAPIProcessor - OAuth API 处理 (跳过)
    ├─→ [3.4] ClaudeWebProcessor - Web 反向代理处理 ✅
    ├─→ [3.5] EventParsingProcessor - SSE 事件解析
    ├─→ [3.6] ModelInjectorProcessor - 模型信息注入
    ├─→ [3.7] StopSequencesProcessor - 停止序列处理
    ├─→ [3.8] ToolCallEventProcessor - 工具调用事件处理
    ├─→ [3.9] MessageCollectorProcessor - 消息收集
    ├─→ [3.10] TokenCounterProcessor - Token 计数
    ├─→ [3.11] StreamingResponseProcessor - 流式响应处理
    └─→ [3.12] NonStreamingResponseProcessor - 非流式响应处理
    ↓
[4] 返回 StreamingResponse 或 JSONResponse
    ↓
客户端接收响应
```

---

## 详细流程说明

### [1] FastAPI 路由入口

**文件**: `app/api/routes/claude.py`

**功能**:
- 接收客户端的 POST 请求到 `/v1/messages` 端点
- 使用 `tenacity` 库进行重试处理（最多 3 次）
- 解析请求体为 `MessagesAPIRequest` 对象
- 进行身份验证（API Key）

**关键代码**:
```python
@router.post("/messages", response_model=None)
@retry(...)
async def create_message(
    request: Request, 
    messages_api_request: MessagesAPIRequest, 
    _: AuthDep
) -> StreamingResponse | JSONResponse:
    context = ClaudeAIContext(
        original_request=request,
        messages_api_request=messages_api_request,
    )
    context = await ClaudeAIPipeline().process(context)
    return context.response
```

---

### [2] 创建 ClaudeAIContext

**作用**:
- 封装请求的所有上下文信息
- 在处理器之间传递数据

**主要属性**:
- `original_request`: 原始 FastAPI Request 对象
- `messages_api_request`: 解析后的 API 请求
- `claude_session`: Claude.ai 会话对象
- `claude_web_request`: 构建的 Web 请求
- `original_stream`: Claude.ai 返回的原始 SSE 流
- `event_stream`: 解析后的事件流
- `collected_message`: 收集到的完整消息
- `response`: 最终返回的响应对象

---

### [3] ClaudeAIPipeline 处理器管道

**文件**: `app/processors/claude_ai/pipeline.py`

处理器按顺序执行，每个处理器可以：
- 读取和修改 `context` 对象
- 跳过处理（如果不满足条件）
- 抛出异常（触发重试或错误处理）

---

#### [3.1] TestMessageProcessor

**功能**: 处理 SillyTavern 兼容性测试消息
- 检查是否为测试消息 (text=true 且 messages=null)
- 直接返回成功响应，跳过后续处理

---

#### [3.2] ToolResultProcessor

**功能**: 处理工具调用结果
- 将 `tool_result` 类型的消息内容转换为 Claude 可识别的格式
- 处理图片附件

---

#### [3.3] ClaudeAPIProcessor

**功能**: OAuth API 模式处理器
- **本项目不使用**，直接跳过
- 如果需要使用 OAuth，会在此处调用官方 Anthropic API

---

#### [3.4] ClaudeWebProcessor ✅ **核心处理器**

**文件**: `app/processors/claude_ai/claude_web_processor.py`

**功能**: 处理 Web 反向代理模式的核心逻辑

**详细步骤**:

1. **获取或创建 Claude 会话**:
   ```python
   context.claude_session = await session_manager.get_or_create_session(session_id)
   ```
   - 使用 `session_manager` 管理会话生命周期
   - 会话包含 cookies、账户信息等
   - 初始化时会创建或获取 conversation_id

2. **构建 ClaudeWebRequest**:
   ```python
   # 合并消息文本和系统提示
   merged_text, images = await process_messages(request.messages, request.system)
   
   # 添加填充文本（如果配置）
   if settings.padtxt_length > 0:
       pad_text = "".join(random.choices(pad_tokens, k=settings.padtxt_length))
       merged_text = pad_text + merged_text
   
   # 上传图片
   for image in images:
       file_id = await context.claude_session.upload_file(...)
       image_file_ids.append(file_id)
   
   # 设置思维模式（Pro 账户）
   paprika_mode = "extended" if (is_pro and thinking.enabled) else None
   await context.claude_session.set_paprika_mode(paprika_mode)
   
   # 构建请求对象
   web_request = ClaudeWebRequest(
       max_tokens_to_sample=request.max_tokens,
       attachments=[Attachment.from_text(merged_text)],
       files=image_file_ids,
       model=request.model,
       tools=request.tools or [],
       ...
   )
   ```

3. **发送请求到 Claude.ai**:
   ```python
   context.original_stream = await context.claude_session.send_message(request_dict)
   ```
   - 使用 `rnet` 库模拟浏览器发送请求
   - 返回 SSE (Server-Sent Events) 流

**Session 管理**:
- 每个 session 对应一个 Claude.ai 对话
- 保持 cookies 和 conversation_id
- 自动处理 session 过期和重新创建

---

#### [3.5] EventParsingProcessor

**文件**: `app/processors/claude_ai/event_parser_processor.py`

**功能**: 解析 SSE 流为结构化事件对象

**处理流程**:
```python
context.event_stream = self.parser.parse_stream(context.original_stream)
```

**事件类型**:
- `MessageStartEvent`: 消息开始
- `ContentBlockStartEvent`: 内容块开始（文本、工具调用等）
- `ContentBlockDeltaEvent`: 内容块增量更新
- `ContentBlockStopEvent`: 内容块结束
- `MessageDeltaEvent`: 消息元数据更新（stop_reason、token 使用等）
- `MessageStopEvent`: 消息结束
- `ErrorEvent`: 错误事件

---

#### [3.6] ModelInjectorProcessor

**功能**: 注入模型信息到响应中
- 在 `MessageStartEvent` 中添加实际使用的模型名称

---

#### [3.7] StopSequencesProcessor

**功能**: 处理自定义停止序列
- 检查生成的文本是否包含用户定义的停止序列
- 截断文本并设置 `stop_reason="stop_sequence"`

---

#### [3.8] ToolCallEventProcessor

**功能**: 处理工具调用事件
- 转换 Claude.ai 的工具调用格式为标准 API 格式
- 处理 `tool_use` 和 `tool_result` 内容块

---

#### [3.9] MessageCollectorProcessor ✅ **重要**

**文件**: `app/processors/claude_ai/message_collector_processor.py`

**功能**: 收集流式事件为完整的 Message 对象

**处理逻辑**:
```python
async for event in event_stream:
    if isinstance(event.root, MessageStartEvent):
        context.collected_message = event.root.message
    
    elif isinstance(event.root, ContentBlockStartEvent):
        context.collected_message.content[event.root.index] = event.root.content_block
    
    elif isinstance(event.root, ContentBlockDeltaEvent):
        # 增量更新内容（文本、thinking、tool input 等）
        self._apply_delta(content_block, event.root.delta)
    
    elif isinstance(event.root, ContentBlockStopEvent):
        # 解析 JSON（tool_use.input, tool_result.content）
        if isinstance(block, ToolUseContent):
            block.input = json5.loads(block.input_json)
    
    elif isinstance(event.root, MessageDeltaEvent):
        # 更新 stop_reason、token 使用等
        context.collected_message.stop_reason = event.root.delta.stop_reason
        context.collected_message.usage = event.root.usage
        
        # 处理 refusal 响应
        if stop_reason == "refusal" and not content:
            yield ErrorEvent(...)
    
    # 不消费事件，继续传递给下游
    yield event
```

**特殊处理**:
- **Refusal 响应**: 当 Claude 拒绝回答时，注入友好的错误提示
- **JSON5 解析**: 支持更宽松的 JSON 格式，自动回退到标准 JSON
- **边界检查**: 防止 refusal 响应导致的 IndexError

---

#### [3.10] TokenCounterProcessor

**功能**: 计算 token 使用量
- 使用 `tiktoken` 库估算输入和输出 token
- 在响应中添加 usage 信息

---

#### [3.11] StreamingResponseProcessor ✅

**文件**: `app/processors/claude_ai/streaming_response_processor.py`

**功能**: 创建流式响应

**条件**: `messages_api_request.stream == True`

**处理流程**:
```python
sse_stream = self.serializer.serialize_stream(context.event_stream)
context.response = StreamingResponse(
    sse_stream,
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    },
)
```

**SSE 格式**:
```
event: message_start
data: {"type":"message_start","message":{...}}

event: content_block_delta
data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}

event: message_stop
data: {"type":"message_stop"}
```

---

#### [3.12] NonStreamingResponseProcessor

**功能**: 创建非流式 JSON 响应

**条件**: `messages_api_request.stream == False` 或未指定

**处理流程**:
```python
# 等待 event_stream 完全消费
async for _ in context.event_stream:
    pass

# 返回完整的 Message 对象
context.response = JSONResponse(
    content=context.collected_message.model_dump(exclude_none=True)
)
```

---

### [4] 返回响应

**StreamingResponse** (流式):
- 客户端逐步接收 SSE 事件
- 适用于实时显示生成过程

**JSONResponse** (非流式):
- 客户端一次性接收完整消息
- 适用于获取完整响应内容

---

## 错误处理

### 网络错误
- `ConnectionError`, `TimeoutError`: 转换为 `AppError` 并返回友好提示
- 自动重试（最多 3 次，间隔 1 秒）

### Session 管理错误
- Session 过期: 自动清理并创建新 session
- 账户配额耗尽: 切换到下一个可用账户

### 特殊响应
- **Refusal**: Claude 拒绝回答时，返回友好错误提示
- **空响应**: 抛出 `NoResponseError`

---

## 关键组件

### Session Manager
**文件**: `app/services/session.py`

**功能**:
- 管理 Claude.ai 会话的生命周期
- 缓存 session 对象（避免重复创建）
- 自动清理过期 session

### Claude Session
**文件**: `app/core/claude_session.py`

**功能**:
- 封装与 Claude.ai 的交互
- 管理 conversation_id 和 cookies
- 提供消息发送、文件上传等方法

### HTTP Client
**文件**: `app/core/http_client.py`

**功能**:
- 封装 `rnet` 和 `curl-cffi` 客户端
- 自动重试和错误处理
- 模拟浏览器行为（User-Agent, 指纹等）

---

## 配置说明

### 关键配置项

**会话管理**:
- `SESSION_EXPIRY_SECONDS`: Session 过期时间（默认 3600 秒）

**重试配置**:
- `RETRY_ATTEMPTS`: 请求重试次数（默认 3）
- `RETRY_INTERVAL`: 重试间隔（默认 1 秒）

**请求配置**:
- `PADTXT_LENGTH`: 填充文本长度（防止指纹识别）
- `PAD_TOKENS`: 填充字符集
- `CUSTOM_PROMPT`: 自定义系统提示

**账户管理**:
- 支持多账户轮换
- 自动跟踪配额使用

---

## 调试建议

### 查看日志
```python
logger.debug(f"Session ID: {context.claude_session.session_id}")
logger.debug(f"Web request: {context.claude_web_request.model_dump()}")
```

### 关键日志位置
1. `ClaudeWebProcessor`: 会话创建、请求构建
2. `EventParsingProcessor`: SSE 事件解析
3. `MessageCollectorProcessor`: 消息收集、refusal 处理
4. `StreamingResponseProcessor`: 响应生成

### 常见问题
- **timeout 错误**: 检查 `http_client.py` 中的 timeout 配置
- **session 无效**: 检查 cookies 是否过期
- **refusal 响应**: 检查消息内容是否触发安全过滤

---

## 总结

本项目的请求处理流程核心是：

1. **接收标准 Anthropic API 请求**
2. **转换为 Claude.ai Web 格式**（通过 ClaudeWebProcessor）
3. **模拟浏览器发送请求**（使用 rnet）
4. **解析 SSE 流**（EventParsingProcessor）
5. **收集和转换响应**（MessageCollectorProcessor）
6. **返回标准 API 格式**（StreamingResponseProcessor 或 NonStreamingResponseProcessor）

整个过程对客户端完全透明，客户端只需要按照标准 Anthropic API 格式发送请求即可。
