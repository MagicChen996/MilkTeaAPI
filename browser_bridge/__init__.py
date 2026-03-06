# 浏览器桥接：通过 CDP 连接本机已打开的浏览器，在 AI 网页对话里输入并取回复（MilkTea API）

from .automation import BrowserBridge, BridgeConfig, create_bridge_from_config

__all__ = ["BrowserBridge", "BridgeConfig", "create_bridge_from_config"]
