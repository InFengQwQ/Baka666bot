"""Run OneBot V11-oriented plugins on Discord and Telegram.

Foreign message events are converted to OneBot V11 events before matcher
dispatch. Plugin output is translated back through the native adapter.
"""

from __future__ import annotations

from nonebot import require
from nonebot.rule import Rule

require("nonebot_plugin_waiter")
require("nonebot_plugin_alconna")

from .framework import is_foreign_bot

foreign_adapter = Rule(is_foreign_bot)

from . import bridge  # noqa: E402,F401
