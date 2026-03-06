# MilkTea API 🧋

通过 **浏览器** 里已打开的 AI ToC 对话页（豆包、千问等 Web 端）进行输入，并把页面上的回复通过 HTTP API 返回，无需桌面客户端、无需 OCR。

## 功能

1. **提供 API**：提供类似 OpenAI 的接口（`/v1/chat/completions`），便于现有应用调用。
2. **桥接浏览器页面**：你打开一个浏览器，里面是各种 AI 的 Web 端对话窗口；本服务通过 **Chrome DevTools Protocol (CDP)** 连接该浏览器，在对应页面的输入框里输入、发送，并读取回复区域的文本，再通过 API 返回。

## 环境要求

- Python 3.10+
- 浏览器需以 **远程调试** 方式启动（如 Chrome `--remote-debugging-port=9222`），并已打开目标 AI 对话页（如豆包 Web、千问 Web）。

## 安装

```bash
git clone <你的仓库地址>
cd milkteaAPI
pip install -r requirements.txt
playwright install chromium
```

（若只连接已有浏览器、不自行启动 Chromium，理论上可不执行 `playwright install`，但建议执行一次以免缺驱动。）

## 快速开始（推荐步骤）

按以下顺序操作即可把本插件跑起来，并与 OpenClaw 等客户端配合使用。

### 第一步：关闭所有 Chrome 浏览器

请先**完全退出**所有 Chrome 窗口（包括后台进程），否则远程调试端口可能冲突。可在任务管理器中确认没有 `chrome.exe` 在运行。

### 第二步：启动带调试端口的 Chrome

双击运行项目根目录下的 **`ChromeRemoteDebugger.bat`**：

- 脚本会以远程调试模式（`--remote-debugging-port=9222`）启动一个新的 Chrome 窗口。
- 启动后不要关闭该窗口，豆包/千问等页面必须在这个窗口里打开。
- 如需确认调试是否生效，可在浏览器访问：<http://127.0.0.1:9222/json>，能看到 JSON 即表示正常。

### 第三步：在浏览器中打开千问（或豆包）

在**刚才弹出的 Chrome 窗口**里，打开目标 AI 对话页，例如：

- **千问**：<https://qianwen.aliyun.com/> 或通义千问 Web 版
- **豆包**：豆包 Web 对话页

并进入一个对话界面，保持该标签页为当前页。

### 第四步：启动本插件（MilkTea API 服务）

双击运行 **`run.bat`**，或在本项目目录下执行：

```bash
python main.py
```

终端会显示 MilkTea API 的启动信息与地址。服务默认监听：<http://127.0.0.1:8765>。

- API 文档：<http://127.0.0.1:8765/docs>
- 聊天接口：`POST http://127.0.0.1:8765/v1/chat/completions`

---

## 配置

编辑 `config.yaml`：

- **server**：API 监听 `host` / `port`，默认 `127.0.0.1:8765`。
- **browser.cdp_url**：浏览器 CDP 地址，默认 `http://127.0.0.1:9222`。
- **client**：`auto`（自动匹配标签页）或 `doubao_web` / `qwen_web`。
- **clients.xxx**：每个站点的
  - `url_contains`：当前标签页 URL 包含该字符串即视为该站点。
  - `input_selector`：输入框的 CSS 选择器（如 `textarea` 或 `[role="textbox"][contenteditable="true"]`）。
  - `send_key` / `send_selector`：发送方式（按键或点击按钮）。
  - `response_selector`：**回复内容所在元素的 CSS 选择器**，会取**最后一个**匹配元素的文本作为回复。
  - `response_wait_timeout`：等待回复的最大秒数。

页面结构不同时，只需改对应站点的选择器即可，无需改代码。

## API 示例

```bash
curl -X POST "http://127.0.0.1:8765/v1/chat/completions" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"doubao\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
```

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="none")
r = client.chat.completions.create(model="doubao", messages=[{"role": "user", "content": "你好"}])
print(r.choices[0].message.content)
```

## OpenClaw 配置

本服务提供与 **Ollama** 相同的 OpenAI 兼容 API（`/v1/chat/completions`、`/v1/models`），可被 [OpenClaw](https://docs.openclaw.ai/) 作为「自定义模型」调用。

1. 先按上文 **「快速开始」** 完成：关闭 Chrome → 运行 `ChromeRemoteDebugger.bat` → 在浏览器中打开千问（或豆包）→ 运行 `run.bat` 启动本插件。
2. 在 **OpenClaw** 安装或配置模型时：
   - 选择 **「自定义模型」**（或类似「自定义 / 本地 API」）选项。
   - 在 API 地址处填写**本插件的本地地址**，例如：  
     **`http://127.0.0.1:8765/v1`**  
     （若你修改了 `config.yaml` 中的 `server.port`，请改为对应端口，路径保持 `/v1`。）
3. 若 OpenClaw 支持手动配置提供商，可参考如下（baseUrl 即上述插件地址）：

```json5
{
  models: {
    providers: {
      browser_bridge: {
        baseUrl: "http://127.0.0.1:8765/v1",
        apiKey: "ollama-local",
        api: "openai-completions",
        models: [
          { id: "doubao", name: "豆包", contextWindow: 8192, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, maxTokens: 8192 },
          { id: "qwen", name: "千问", contextWindow: 8192, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, maxTokens: 8192 }
        ]
      }
    }
  }
}
```

4. 在 agent 的 `model` 中选用 `browser_bridge/doubao` 或 `browser_bridge/qwen`（与 `GET /v1/models` 返回的 `id` 一致）。

错误时接口返回 OpenAI 风格 `{ "error": { "message": "...", "type": "api_error", "code": "..." } }`，便于 OpenClaw 正确解析。

## 选择器说明

- **input_selector**：页面上**唯一**或**主要**的输入框（如 `textarea`、`[contenteditable=true]`、`[role="textbox"]`）。若页面有多个输入框，需写更具体的选择器。
- **response_selector**：**AI 回复气泡/区块**的 CSS 选择器；会取**所有匹配元素中最后一个**的 `innerText` 作为本次回复。若站点是流式输出，会多等约 1.5 秒再取，以减少未打完就返回的情况。  
  若豆包/千问改版导致选择器失效，在浏览器开发者工具里查看回复区域的 class 或 data 属性，更新 `config.yaml` 中对应站点的 `response_selector` 即可。

## 项目结构

```
milkteaAPI/
├── config.yaml              # 服务与各站点选择器配置
├── main.py                  # 主入口（含启动横幅）
├── api_server.py            # FastAPI + OpenAI 兼容接口
├── browser_bridge/          # 浏览器 CDP 桥接
│   ├── __init__.py
│   └── automation.py
├── requirements.txt
├── ChromeRemoteDebugger.bat # 以远程调试模式启动 Chrome（运行前请先关闭所有 Chrome）
├── run.bat                  # 启动 MilkTea API 服务
└── README.md
```

## 许可证

MIT
