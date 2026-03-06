# -*- coding: utf-8 -*-
"""
通过 Chrome DevTools Protocol (CDP) 连接用户已打开的浏览器，
在 AI 网页对话（如豆包/千问 Web 端）中输入消息并读取回复（MilkTea API）。
"""
import asyncio
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Union, List

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
except ImportError:
    async_playwright = None
    Browser = None
    Page = None
    BrowserContext = None


@dataclass
class BridgeConfig:
    """单个站点（如豆包 Web）的桥接配置"""
    url_contains: Union[str, List[str]]  # 匹配标签页 URL，支持多个关键词（任一匹配即可）
    input_selector: str        # 输入框 CSS 选择器，如 "textarea"、"[contenteditable=true]"
    send_key: Optional[str] = "Enter"   # 发送方式：按键，如 "Enter"
    send_selector: Optional[str] = None # 或点击按钮的选择器，优先于 send_key
    response_selector: str = "" # 回复内容所在元素，取最后一个的文本
    response_wait_timeout: int = 60
    response_stream_stable_sec: int = 0  # EventStream 流式：内容稳定不再变化后等待秒数再取，0 表示不等待


class BrowserBridge:
    """
    连接至已开启远程调试的浏览器，在指定页面的输入框输入并获取 AI 回复。
    """

    def __init__(self, cdp_url: str, config: BridgeConfig):
        self.cdp_url = cdp_url.rstrip("/")
        if not self.cdp_url.startswith("http"):
            self.cdp_url = "http://" + self.cdp_url
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._last_connect_error: Optional[str] = None
        self._cached_page: Optional[Page] = None  # 首次匹配到的标签页，后续复用避免顺序变化
        self._client_key: Optional[str] = None  # 用于调试日志，由 create_bridge_from_config 设置

    async def connect(self) -> bool:
        """通过 CDP 连接已有浏览器"""
        self._last_connect_error = None
        if async_playwright is None:
            self._last_connect_error = "未安装 playwright"
            return False
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
            # CDP 连接后 contexts/pages 有时会稍晚就绪，短暂等待
            await asyncio.sleep(1.0)
            return True
        except Exception as e:
            self._last_connect_error = str(e)
            return False

    async def disconnect(self) -> None:
        self._cached_page = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _url_matches(self, url: str) -> bool:
        """当前配置的 url_contains 是否匹配该 URL"""
        u = (url or "").lower()
        keys = self.config.url_contains
        if isinstance(keys, str):
            keys = [keys]
        return any((k or "").lower() in u for k in keys)

    async def _get_page(self) -> Optional[Page]:
        """根据 url_contains 找到匹配的标签页；命中后缓存该页，后续请求复用同一标签页。"""
        if not self._browser:
            return None
        # #region agent log
        _log_path = Path(__file__).resolve().parent.parent / "debug-64859e.log"
        def _dbg(m: str, data: dict, hyp: str):
            try:
                with open(_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId": "64859e", "timestamp": int(time.time() * 1000), "location": "automation._get_page", "message": m, "data": data, "hypothesisId": hyp}, ensure_ascii=False) + "\n")
            except Exception:
                pass
        # #endregion
        try:
            if self._cached_page is not None and not self._cached_page.is_closed():
                # #region agent log
                _dbg("_get_page: return cached page", {"client_key": getattr(self, "_client_key", None), "page_url": (self._cached_page.url or "")[:80]}, "C")
                # #endregion
                return self._cached_page
        except Exception:
            self._cached_page = None
        keys = self.config.url_contains
        url_contains_preview = (keys[:2] if isinstance(keys, list) else [keys])[:2]
        for ctx in self._browser.contexts:
            for page in ctx.pages:
                try:
                    u = page.url or ""
                    if not u.startswith("http") or "chrome://" in u or "devtools://" in u:
                        continue
                    if self._url_matches(u):
                        self._cached_page = page
                        # #region agent log
                        _dbg("_get_page: return new match", {"client_key": getattr(self, "_client_key", None), "page_url": u[:80], "url_contains_preview": url_contains_preview}, "D")
                        # #endregion
                        return page
                except Exception:
                    pass
        return None

    async def get_all_page_urls(self) -> List[str]:
        """返回当前浏览器所有标签页的 URL（用于报错时提示）"""
        urls = []
        if not self._browser:
            return urls
        for _ in range(2):
            for ctx in self._browser.contexts:
                for page in ctx.pages:
                    try:
                        u = page.url
                        if u and not u.startswith("chrome://") and not u.startswith("devtools://"):
                            urls.append(u)
                    except Exception:
                        pass
            if urls:
                break
            await asyncio.sleep(1.0)
        return urls

    async def send_and_receive(self, user_message: str) -> str:
        """
        在当前站点的页面中：聚焦输入框、输入内容、发送，等待回复并返回回复文本。
        """
        if not self._browser:
            if not await self.connect():
                raise RuntimeError(
                    f"无法通过 CDP 连接浏览器，请确认已用远程调试启动浏览器："
                    f" chrome --remote-debugging-port=9222，且本服务配置的地址为 {self.cdp_url}"
                )
        page = await self._get_page()
        # #region agent log
        try:
            _lp = Path(__file__).resolve().parent.parent / "debug-64859e.log"
            with open(_lp, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId": "64859e", "timestamp": int(time.time() * 1000), "location": "automation.send_and_receive", "message": "send_and_receive: page to use", "data": {"client_key": getattr(self, "_client_key", None), "page_url": ((page.url or "")[:80] if page else None)}, "hypothesisId": "E"}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        if not page:
            urls = await self.get_all_page_urls()
            hint = f"当前浏览器中的标签页 URL：{urls[:10]}" if urls else "当前没有可用的非 chrome 内置页"
            raise RuntimeError(
                f"未找到匹配「{self.config.url_contains}」的标签页。{hint}。"
                "请在 config.yaml 的 url_contains 中填写你实际打开的对话页 URL 里的关键词（可写多个）。"
            )

        # 把对应模型的标签页切到前台，方便用户看到正在操作的是哪个
        try:
            await page.bring_to_front()
        except Exception:
            pass

        cfg = self.config
        input_sel = cfg.input_selector
        timeout_ms = cfg.response_wait_timeout * 1000

        try:
            await page.wait_for_selector(input_sel, timeout=10000)
        except Exception as e:
            raise RuntimeError(f"页面上未找到输入框（选择器: {input_sel}）: {e}") from e

        await page.click(input_sel)
        await asyncio.sleep(0.15)
        await page.fill(input_sel, "")
        await asyncio.sleep(0.05)
        await page.fill(input_sel, user_message)
        await asyncio.sleep(0.1)

        if cfg.send_selector:
            try:
                await page.click(cfg.send_selector, timeout=5000)
            except Exception:
                if cfg.send_key:
                    await page.keyboard.press(cfg.send_key)
        elif cfg.send_key:
            await page.keyboard.press(cfg.send_key)

        if not cfg.response_selector:
            raise ValueError("config 中 response_selector 不能为空，请配置回复内容所在元素的 CSS 选择器")

        # 等待出现回复元素，多等一会让流式输出稳定后再取
        try:
            await page.wait_for_selector(cfg.response_selector, timeout=timeout_ms)
        except Exception as e:
            raise TimeoutError(
                f"在 {cfg.response_wait_timeout} 秒内未检测到回复元素（选择器: {cfg.response_selector}），请检查页面结构或增大 response_wait_timeout"
            ) from e

        await asyncio.sleep(2.0)

        # EventStream 流式：若配置了 response_stream_stable_sec，轮询直到内容稳定
        stable_sec = getattr(cfg, "response_stream_stable_sec", 0) or 0
        if stable_sec > 0:
            last_text = ""
            stable_since = 0.0
            poll_interval = 1.0
            max_wait = 25
            waited = 0.0
            while waited < max_wait:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                elements = await page.query_selector_all(cfg.response_selector)
                if not elements:
                    continue
                try:
                    text = (await elements[-1].inner_text() or "").strip()
                except Exception:
                    continue
                if text == last_text and len(text) >= 2:
                    stable_since = stable_since or waited
                    if waited - stable_since >= stable_sec:
                        return text[:8000]
                else:
                    stable_since = 0.0
                last_text = text

        await asyncio.sleep(0.5)
        user_msg_trimmed = (user_message or "").strip()[:500]

        for attempt in range(2):
            elements = await page.query_selector_all(cfg.response_selector)
            if not elements:
                if attempt == 0:
                    await asyncio.sleep(2.0)
                    continue
                raise RuntimeError(f"未找到任何匹配回复选择器的元素: {cfg.response_selector}")

            # 规律：新回复总是追加在 DOM 末尾，取最后一个匹配元素即为本次回复（不按“最长”选，避免拿到历史长回复）
            last_el = elements[-1]
            try:
                reply = (await last_el.inner_text() or "").strip()
            except Exception:
                reply = ""
            if reply and len(reply) >= 2:
                if user_msg_trimmed and (reply == user_msg_trimmed or (user_msg_trimmed in reply and len(reply) < len(user_msg_trimmed) + 50)):
                    pass
                else:
                    return reply[:8000]

            # 若最后一个为空或疑似用户消息，再按“最长且非用户消息”兜底
            texts_with_len = []
            for el in elements:
                try:
                    t = (await el.inner_text() or "").strip()
                    if not t:
                        continue
                    if user_msg_trimmed and (t == user_msg_trimmed or (user_msg_trimmed in t and len(t) < len(user_msg_trimmed) + 50)):
                        continue
                    texts_with_len.append((len(t), t))
                except Exception:
                    continue
            if texts_with_len:
                texts_with_len.sort(key=lambda x: -x[0])
                reply = texts_with_len[0][1][:8000]
                if len(reply) >= 2:
                    return reply

            if attempt == 0:
                await asyncio.sleep(2.0)
                continue

        text = (await last_el.inner_text() or "").strip()
        return text[:8000]


def create_bridge_from_config(
    client_key: str,
    clients_config: dict,
    cdp_url: str,
    response_wait_timeout: int = 60,
) -> BrowserBridge:
    """从 config 中的 clients 配置创建 BrowserBridge"""
    cfg = clients_config.get(client_key)
    if not cfg:
        raise ValueError(f"未知客户端: {client_key}，可选: {list(clients_config.keys())}")
    bridge_cfg = BridgeConfig(
        url_contains=cfg.get("url_contains", client_key),
        input_selector=cfg.get("input_selector", "textarea"),
        send_key=cfg.get("send_key"),
        send_selector=cfg.get("send_selector"),
        response_selector=cfg.get("response_selector", ""),
        response_wait_timeout=cfg.get("response_wait_timeout", response_wait_timeout),
        response_stream_stable_sec=int(cfg.get("response_stream_stable_sec", 0) or 0),
    )
    bridge = BrowserBridge(cdp_url=cdp_url, config=bridge_cfg)
    bridge._client_key = client_key
    return bridge
