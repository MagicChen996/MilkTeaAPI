# -*- coding: utf-8 -*-
"""
MilkTea API：将请求转发到本机浏览器里已打开的 AI 网页对话，返回 OpenAI 兼容的 API 回复。
"""
import asyncio
import json
import time
from typing import Optional, List, Literal, Union, Any
import yaml
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

# #region agent log
def _dbg(m: str, data: dict, hyp: str, loc: str):
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "64859e", "timestamp": int(time.time() * 1000), "location": loc, "message": m, "data": data, "hypothesisId": hyp}, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
DEBUG_LOG_PATH = CONFIG_PATH.parent / "debug-64859e.log"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 请求里 model 与 config clients 的对应关系（短名 -> client_key）
MODEL_TO_CLIENT = {"qwen": "qwen_web", "doubao": "doubao_web"}

# 按 client_key 缓存 bridge，避免重复连接
_bridges: dict = {}


def _model_to_client_key(model: Optional[str], clients: dict) -> Optional[str]:
    """把请求里的 model 转成 config 的 client_key。支持 qwen、qwen-web、qwen_web 等。"""
    if not model or not clients:
        return None
    raw = model.strip().lower().replace("-", "_")
    if raw in clients:
        return raw
    return MODEL_TO_CLIENT.get(raw)


async def get_bridge(model: Optional[str] = None):
    """根据 config 与请求的 model 创建并连接 BrowserBridge（支持 auto）。model 决定操作哪个站点的标签页。"""
    from browser_bridge import BrowserBridge, create_bridge_from_config

    global _bridges
    cfg = load_config()
    cdp_url = (cfg.get("browser") or {}).get("cdp_url") or "http://127.0.0.1:9222"
    clients = cfg.get("clients", {})
    client_conf = (cfg.get("client") or "auto").strip().lower()
    timeout = cfg.get("response_wait_timeout", 90)

    # 请求指定了 model 时，解析出对应的 client_key（qwen-web / qwen_web / qwen -> qwen_web）
    try_key = _model_to_client_key(model, clients)
    # #region agent log
    _dbg("get_bridge: model -> try_key", {"model": model, "try_key": try_key, "client_conf": client_conf, "cached_keys": list(_bridges.keys())}, "A", "api_server.get_bridge")
    # #endregion

    async def _get_or_create_bridge(client_key: str):
        if client_key not in clients:
            return None
        bridge = create_bridge_from_config(client_key, clients, cdp_url, response_wait_timeout=timeout)
        if not await bridge.connect():
            await bridge.disconnect()
            return None
        page = await bridge._get_page()
        if not page:
            await bridge.disconnect()
            return None
        return bridge

    # 若指定了 model 且能映射到 client_key，只尝试该站点（先查缓存）
    if try_key and try_key in clients:
        if try_key in _bridges:
            cached_bridge = _bridges[try_key]
            # 确保缓存的 bridge 确实是对应 try_key 的，防止误用其它站点的 bridge
            if getattr(cached_bridge, "_client_key", None) == try_key:
                # #region agent log
                _dbg("get_bridge: return cached", {"try_key": try_key}, "B", "api_server.get_bridge")
                # #endregion
                return cached_bridge
            del _bridges[try_key]
        bridge = await _get_or_create_bridge(try_key)
        if bridge:
            _bridges[try_key] = bridge
            # #region agent log
            _dbg("get_bridge: return new bridge", {"try_key": try_key}, "B", "api_server.get_bridge")
            # #endregion
            return bridge
        urls = []
        try:
            tmp = create_bridge_from_config(try_key, clients, cdp_url, response_wait_timeout=timeout)
            if await tmp.connect():
                urls = await tmp.get_all_page_urls()
            await tmp.disconnect()
        except Exception:
            pass
        hint = f"未找到匹配「{try_key}」的标签页。" + (f" 当前标签页 URL：{urls[:10]}" if urls else " 请在该调试浏览器中打开千问/豆包对应页面。")
        raise RuntimeError(hint)

    # 未指定 model 或映射不到：按 config 的 client 处理
    # #region agent log
    _dbg("get_bridge: using auto path", {"try_key": try_key, "client_conf": client_conf}, "A", "api_server.get_bridge")
    # #endregion
    if client_conf == "auto":
        for key in ("doubao_web", "qwen_web"):
            if key in _bridges:
                return _bridges[key]
            bridge = await _get_or_create_bridge(key)
            if bridge:
                _bridges[key] = bridge
                return bridge
        first_key = next(iter(clients)) if clients else None
        if first_key:
            tmp = create_bridge_from_config(first_key, clients, cdp_url, response_wait_timeout=timeout)
            if not await tmp.connect():
                err = getattr(tmp, "_last_connect_error", "") or "未知错误"
                await tmp.disconnect()
                hint = ""
                if "ECONNREFUSED" in err or "refused" in err.lower():
                    hint = (
                        "本机 9222 端口无程序监听。请先完全关闭所有 Chrome 窗口，再单独用命令行启动："
                        ' "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 。'
                        "启动后用该窗口打开豆包/千问。在浏览器地址栏访问 http://127.0.0.1:9222/json 若能看到 JSON 即表示调试已开启。"
                    )
                else:
                    hint = "请确认：1) 已用 chrome --remote-debugging-port=9222 启动浏览器；2) 豆包/千问在「该调试窗口」里打开；3) 9222 端口可访问。"
                raise RuntimeError(f"无法通过 CDP 连接浏览器（{cdp_url}）。错误：{err}。{hint}")
            urls = await tmp.get_all_page_urls()
            await tmp.disconnect()
            if not urls:
                raise RuntimeError(
                    "已连接浏览器但未发现任何标签页（contexts/pages 为空）。"
                    "请确认豆包/千问是在「用 --remote-debugging-port=9222 启动的」那个 Chrome 窗口里打开的，而不是另一个未带调试的窗口。"
                )
            raise RuntimeError(
                "未找到匹配的标签页。请根据下方实际 URL，在 config.yaml 里对应站点的 url_contains 中加上能匹配的关键词。"
                "当前标签页 URL：" + str(urls[:15])
            )
        raise RuntimeError(
            "未找到匹配的标签页。请先用远程调试启动浏览器（如 chrome --remote-debugging-port=9222），"
            "打开豆包/千问等 AI 对话页并保持在该页。"
        )
    if client_conf in _bridges:
        return _bridges[client_conf]
    bridge = await _get_or_create_bridge(client_conf)
    if not bridge:
        raise RuntimeError(f"无法连接或未找到匹配的标签页（client={client_conf}）。请确认该站点页面已在调试浏览器中打开。")
    _bridges[client_conf] = bridge
    return bridge


# --- Pydantic（OpenAI 兼容）---
# content 支持字符串或 OpenAI content parts 数组（OpenClaw 等会发 [{"type":"text","text":"..."}]）

def _content_to_str(content: Union[str, List[Any], None]) -> str:
    """将 content 规范为字符串：纯字符串直接返回，parts 数组只取 type=text 的 text 拼接。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            (p.get("text") or "").strip()
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    return ""


def _strip_timestamp_prefix(line: str) -> str:
    """去掉行首 [Thu 2026-03-05 16:47 GMT+8] 这类时间戳，保留后面正文。如 '[Thu ...]哈哈哈' -> '哈哈哈'"""
    t = line.strip()
    if t.startswith("[") and "]" in t:
        rest = t.split("]", 1)[-1].strip()
        return rest
    return t


def _body_only(raw: str) -> str:
    """只保留正文：去掉 OpenClaw 的 Sender (untrusted metadata) 块，正文可能在块前或块后；时间戳与正文在同一行时只保留正文。"""
    if not raw or not raw.strip():
        return raw
    text = raw.strip()
    # OpenClaw 格式常为：先 metadata 块，正文在块后（如 [Thu ...]哈哈哈），或正文在块前
    if "Sender (untrusted metadata):" in text:
        before = text.split("Sender (untrusted metadata):")[0].strip()
        after_block = text.split("Sender (untrusted metadata):", 1)[1]
        # 跳过 ```json ... ```，取块后的内容作为“块后正文”
        if "```" in after_block:
            # 找到结束的 ```
            parts = after_block.split("```")
            # parts[0] 是 ```json 到第一个 ``` 之间的（含 json），parts[1] 是第一个 ``` 之后、下一个 ``` 之前…
            # 简单按 ``` 拆：通常为 [ '', 'json\n{...}', '\n[Thu ...]哈哈哈' ] 或类似
            after_parts = [p.strip() for p in parts[1:] if p.strip() and not p.strip().startswith("json")]
            after_body = "\n".join(after_parts).strip() if after_parts else ""
        else:
            after_body = after_block.strip()
        # 块前有内容则优先当作正文（用户先打字再带 metadata 的情况少见）；否则用块后
        if before:
            text = before
        else:
            text = after_body
    # 去掉残留的 ```json ... ``` 块
    if "```json" in text:
        before, _, rest = text.partition("```json")
        if "```" in rest:
            _, _, after = rest.partition("```")
            text = (before.strip() + "\n" + after.strip()).strip()
        else:
            text = before.strip()
    # 每行去掉行首时间戳，并丢弃“纯时间戳行”（后面无正文）
    lines = []
    for ln in text.splitlines():
        stripped = _strip_timestamp_prefix(ln)
        if _is_metadata_timestamp_line(ln) and not stripped:
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip() or raw.strip()


def _is_metadata_timestamp_line(line: str) -> bool:
    """是否为 OpenClaw 等的时间戳行（整行仅时间戳或时间戳+数字），如 [Thu 2026-03-05 16:41 GMT+8] 1"""
    t = line.strip()
    if len(t) > 80 or not t:
        return False
    if t.startswith("[") and "]" in t:
        tail = t.split("]", 1)[-1].strip()
        if not tail or tail.isdigit() or (len(tail) <= 3 and tail.replace(" ", "").isdigit()):
            return True
    return False


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Union[str, List[dict]]  # 字符串或 OpenAI 多模态 content parts


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="doubao", description="模型名，可任意")
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = "browser-bridge-1"
    object: str = "chat.completion"
    created: int = 0  # Unix timestamp, Ollama/OpenAI 兼容
    model: str = "doubao"
    choices: List[ChatChoice]
    usage: dict = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


# --- FastAPI（Ollama/OpenAI 兼容错误体）---

app = FastAPI(
    title="MilkTea API",
    description="将 API 请求转发到本机浏览器中已打开的 AI 对话网页（豆包/千问等），返回页面回复。OpenAI/Ollama 兼容。",
    version="2.0.0",
)


def _openai_error_body(message: str, code: str = "api_error", typ: str = "api_error") -> dict:
    return {"error": {"message": message, "type": typ, "code": code}}


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    code = "invalid_request_error" if 400 <= exc.status_code < 500 else "api_error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_openai_error_body(exc.detail or "Unknown error", code=code),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    msg = exc.errors() and str(exc.errors()) or "Invalid request body"
    return JSONResponse(
        status_code=422,
        content=_openai_error_body(msg, code="invalid_request_error"),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=_openai_error_body(str(exc), code="internal_error"),
    )

async def _get_bridge(model: Optional[str] = None):
    """按请求的 model 获取对应站点的 bridge（qwen -> 千问，doubao -> 豆包）。"""
    return await get_bridge(model=model)


@app.on_event("startup")
async def startup():
    # 不再预热 bridge，避免先缓存 doubao_web 导致后续请求 qwen 时误用豆包标签页
    pass


@app.get("/")
async def root():
    return {"service": "milktea-api", "ollama_compatible_api": "/v1", "docs": "/docs", "openapi": "/openapi.json"}


@app.get("/v1/models")
async def list_models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": "doubao", "object": "model", "created": now, "owned_by": "browser-bridge"},
            {"id": "qwen", "object": "model", "created": now, "owned_by": "browser-bridge"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    parts = []
    for m in req.messages:
        text = _content_to_str(m.content)
        if not text:
            continue
        parts.append(text)
    if not parts:
        raise HTTPException(status_code=400, detail="没有有效消息内容")

    last = req.messages[-1]
    raw = _content_to_str(last.content) if last.role == "user" else "\n".join(parts)
    user_input = _body_only(raw)  # 只把正文发给浏览器，去掉 OpenClaw 的 metadata/时间戳
    if not user_input.strip() and raw.strip():
        user_input = raw.strip()  # 若正文被全滤掉则退回原文，避免发空

    # #region agent log
    _dbg("chat_completions: request model", {"model": req.model}, "A", "api_server.chat_completions")
    # #endregion
    try:
        bridge = await _get_bridge(model=req.model)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    try:
        reply = await bridge.send_and_receive(user_input)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    created_ts = int(time.time())
    if req.stream:
        # OpenClaw 等客户端默认用 stream: true，必须返回 SSE 流式，否则界面不显示回复
        async def _sse_stream():
            chunk_id = f"milktea-{created_ts}"
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': created_ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': reply}, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': created_ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            _sse_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return ChatCompletionResponse(
        created=created_ts,
        model=req.model,
        choices=[
            ChatChoice(index=0, message=ChatMessage(role="assistant", content=reply), finish_reason="stop")
        ],
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )


def run_server(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cfg = load_config()
    server = cfg.get("server", {})
    run_server(host=server.get("host", "127.0.0.1"), port=server.get("port", 8765))
