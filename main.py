# -*- coding: utf-8 -*-
"""
MilkTea API - 主入口。
通过浏览器 CDP 桥接豆包/千问等 AI 对话页，提供 OpenAI 兼容的 HTTP API。
"""
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ANSI 颜色（支持 Windows 10+ 终端）
_C = "\033[36m"   # cyan
_W = "\033[97m"   # white
_G = "\033[90m"   # gray
_R = "\033[0m"    # reset


def _print_banner(host: str, port: int, cdp_ok: bool):
    """打印华丽的启动横幅"""
    base = "http://{}:{}".format(host, port)
    docs = base + "/docs"
    line = "═" * 46
    top = "╔" + line + "╗"
    bot = "╚" + line + "╝"
    empty = "║" + " " * 46 + "║"
    print()
    print(_C + top + _R)
    print(empty)
    print(_C + "║" + _W + "   🧋  M i l k T e a   A P I  🧋   ".center(46) + _C + "║" + _R)
    print(_C + "║" + _G + "   Bridge browser AI chat to OpenAI API   ".center(46) + _C + "║" + _R)
    print(empty)
    print(_C + "║  " + _W + "Server".ljust(12) + _G + base.ljust(32) + _C + "  ║" + _R)
    print(_C + "║  " + _W + "Docs".ljust(12) + _G + docs.ljust(32) + _C + "  ║" + _R)
    print(empty)
    status_text = "CDP ready" if cdp_ok else "CDP not detected"
    print(_C + "║  " + _G + status_text.ljust(44) + _C + "  ║" + _R)
    print(empty)
    print(_C + bot + _R)
    print()


def _check_cdp_port(cdp_url: str) -> bool:
    """检测 CDP 端口是否有程序监听，用于启动时提示。"""
    try:
        base = cdp_url.replace("http://", "").replace("https://", "").rstrip("/")
        url = "http://" + base.split("/")[0] + "/json"
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def main():
    from api_server import load_config, run_server

    cfg = load_config()
    server = cfg.get("server", {})
    cdp_url = (cfg.get("browser") or {}).get("cdp_url") or "http://127.0.0.1:9222"
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8765)
    cdp_ok = _check_cdp_port(cdp_url)
    _print_banner(host, port, cdp_ok)
    if not cdp_ok:
        print(_G + "[提示] 未检测到浏览器调试端口（{}）。请先关闭所有 Chrome，再执行：".format(cdp_url) + _R)
        print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
        print("  然后用弹出的窗口打开豆包/千问。在地址栏访问 http://127.0.0.1:9222/json 可验证是否生效。")
    else:
        print(_G + "已检测到浏览器调试端口，请确保豆包/千问页面在调试窗口中已打开。" + _R)
    print()
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
