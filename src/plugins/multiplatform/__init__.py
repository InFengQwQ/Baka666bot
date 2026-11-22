"""Run OneBot V11-oriented plugins on Discord and Telegram.

Foreign message events are converted to OneBot V11 events before matcher
dispatch. Plugin output is translated back through the native adapter.
"""

from __future__ import annotations

from nonebot import require

require("nonebot_plugin_waiter")
require("nonebot_plugin_alconna")

from . import bridge  # noqa: E402,F401
