---
name: Ollama 式接口兼容 OpenClaw
overview: 在不改变现有浏览器桥接逻辑的前提下，将对外 API 的路径、请求/响应格式、错误格式与 Ollama 的 OpenAI 兼容接口对齐，使 OpenClaw 可通过 baseUrl + openai-completions 方式直接调用本服务。
todos: []
isProject: false
---

# 将接口对齐 Ollama 本地模型方式供 OpenClaw 调用

## 现状与目标

- **当前**：服务已提供 `GET /v1/models` 和 `POST /v1/chat/completions`，语义与 OpenAI 一致，但响应字段与错误体与 Ollama/OpenAI 文档存在细小差异。
- **目标**：接口在路径、请求体、响应体、错误体上与 Ollama 的 OpenAI 兼容 API 一致，使 OpenClaw 像连接 Ollama 一样配置即可使用（`baseUrl: "http://127.0.0.1:8765/v1"`，`api: "openai-completions"`）。

## 差异与改动点

### 1. 响应体字段补齐（与 Ollama/OpenAI 一致）

**POST /v1/chat/completions**

- 在 [api_server.py](d:\projects\MockAPI\api_server.py) 的 `ChatCompletionResponse` 及返回处：
  - 增加 `**created`**：Unix 时间戳（整数），表示响应生成时间。
- 现有 `id`、`object`、`model`、`choices`、`usage` 已满足基本兼容，无需改字段名。

**GET /v1/models**

- 在 [api_server.py](d:\projects\MockAPI\api_server.py) 的 `list_models` 中，为每个 model 对象增加：
  - `**created`**：整数时间戳（如当前时间或固定值），与 Ollama 的「最后修改时间」语义兼容。
  - `**owned_by`**：字符串（如 `"browser-bridge"` 或 `"library"`），与 Ollama 的 `owned_by` 一致。
- 这样 OpenClaw 或其它按 Ollama 文档解析 `/v1/models` 的客户端不会因缺字段报错。

### 2. 错误响应体改为 OpenAI/Ollama 风格

- 当前 FastAPI 对 HTTPException 返回形如 `{ "detail": "..." }`。
- 增加**全局异常处理**：对 4xx/5xx 返回体改为：
  - `{ "error": { "message": "<detail 或异常信息>", "type": "api_error", "code": "<可选，如 invalid_request_error>" } }`
- 实现方式：在 [api_server.py](d:\projects\MockAPI\api_server.py) 中注册 FastAPI 的 `exception_handler`，在 handler 内构造上述 JSON 并设置合适 status_code。

### 3. 请求体兼容（保持现有逻辑）

- 已支持 `model`、`messages`、`stream`、`temperature`、`max_tokens`。
- **stream**：当前仅实现非流式。若请求带 `stream: true`，可：
  - **方案 A（推荐）**：仍返回一次性完整响应（不拆成 SSE），并在响应中忽略或保留 `stream: false` 行为；很多客户端在兼容模式下能接受。
  - **方案 B**：后续若需再实现 SSE 流式输出，再增加分支逻辑。
- 无需为本次「对齐 Ollama 方式」实现流式，仅需保证 `stream: false` 时行为与文档一致。

### 4. 可选：根路径健康检查（与 Ollama 行为类似）

- Ollama 有根路径或健康检查；当前已有 `GET /` 返回服务信息。
- 可保留现状，或为 `GET /` 增加简短说明（如 `"Ollama-compatible API at /v1"`），便于运维确认。非必须。

### 5. 文档与配置说明（README）

- 在 [README.md](d:\projects\MockAPI\README.md) 中增加一节「**OpenClaw 配置**」：
  - 说明本服务提供与 Ollama 相同的 OpenAI 兼容 API（`/v1`）。
  - 给出 OpenClaw 显式配置示例：`baseUrl: "http://127.0.0.1:8765/v1"`、`apiKey: "ollama-local"`（或任意）、`api: "openai-completions"`，以及 `models` 中列出 `doubao` / `qwen` 等（与当前 `GET /v1/models` 返回的 id 一致）。
  - 注明：需先按现有文档用 CDP 打开浏览器并打开对应 AI 对话页，再在 OpenClaw 中选用对应模型。

## 实现顺序建议

1. 在 [api_server.py](d:\projects\MockAPI\api_server.py) 中：为 chat completion 响应增加 `created`；为 `/v1/models` 的每个模型增加 `created`、`owned_by`。
2. 在同一文件中：注册全局 HTTP 异常处理器，将错误响应改为 `{ "error": { "message", "type", "code" } }`。
3. 更新 [README.md](d:\projects\MockAPI\README.md)：添加 OpenClaw 的配置示例与说明。

## 无需改动的部分

- 浏览器桥接逻辑（[browser_bridge/](d:\projects\MockAPI\browser_bridge)）、config.yaml、端口 8765 等保持不变。
- 不新增 Ollama 原生路径（如 `/api/tags`、`/api/show`），因 OpenClaw 的「openai-completions」模式只使用 `/v1/`*；若用户希望隐式发现，可后续再考虑增加 `/api/tags` 等。

## 验收要点

- OpenClaw 中配置 `baseUrl: "http://127.0.0.1:8765/v1"`、`api: "openai-completions"` 及对应 model 后，能列出模型并成功发起对话。
- `curl` 或 Postman 请求 `POST /v1/chat/completions` 与 `GET /v1/models` 时，响应字段与 Ollama 文档中的 OpenAI 兼容描述一致（含 `created`、`owned_by`），错误时返回 `error.message` 形式。

