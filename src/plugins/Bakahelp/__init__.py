"""Bakahelp: a link in chat, a searchable reference on the web."""
import asyncio
from pathlib import Path

from nonebot import get_driver, logger, on_command, on_fullmatch
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State

from .catalog import export_site

from .notices import send_help

__plugin_meta__ = PluginMetadata(
    name="Bakahelp", description="Baka666Bot 指令与触发方式目录",
    usage="消息以 / 开头时自动提示帮助；发送 TD 关闭整个群的自动提示。help 可主动查看。",
)

HELP_URL = "https://malody.top/bakahelp"
help_command = on_command("bakahelp", aliases={"help", "baka帮助"}, priority=1, block=True)
help_text = on_fullmatch(("bakahelp", "help", "baka帮助"), priority=1, block=True)


@help_command.handle()
@help_text.handle()
async def show_help(bot: Bot, event: Event, state: T_State):
    await send_help(bot, event, state, explicit=True)


@get_driver().on_startup
@get_driver().on_bot_connect
async def build_help():
    """All configured plugins have registered by the startup phase."""
    try:
        destination = Path(getattr(get_driver().config, "bakahelp_output_dir", "") or
                           Path(__file__).parent / "dist")
        result = await asyncio.to_thread(export_site, destination,
                                         markdown_path=Path(__file__).resolve().parents[3] / "COMMANDS.md")
        logger.info(f"Bakahelp: exported {result['entry_count']} entries to {destination}")
    except Exception:
        # Documentation failure must not prevent the bot from connecting.
        logger.exception("Bakahelp: help export failed; existing page retained")
