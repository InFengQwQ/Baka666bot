from __future__ import annotations

import importlib

from nonebot import logger, on_command, on_message
from nonebot.adapters import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot.rule import Rule

from . import foreign_adapter
from .framework import PlatformBot, PlatformEvent, is_group_event


HANDLER_PACKAGE = "src.plugins.MalodyVClientPlugin.matcher.handler"

MA_SUBCOMMANDS = {
    "help": "ma_help",
    "profile": "ma_profile",
    "search": "ma_search",
    "rank": "ma_rank",
    "dan": "ma_dan",
    "global": "ma_global",
    "store": "ma_store",
    "event": "ma_event",
    "chart": "ma_chart",
    "friend": "ma_friend",
    "achieve": "ma_achieve",
    "quest": "ma_quest",
    "news": "ma_news",
    "song": "ma_song",
    "wiki": "ma_wiki",
    "logout": "ma_logout",
    "items": "ma_items",
    "marlo": "ma_marlo",
    "activity": "ma_activity",
    "chartrank": "ma_chartrank",
    "eventrank": "ma_eventrank",
    "puzzle": "ma_puzzle",
    "choice": "ma_choice",
    "promote": "ma_promote",
    "skin": "ma_skin",
    "comment": "ma_comment",
    "review": "ma_review",
    "reviewqueue": "ma_reviewqueue",
    "myreview": "ma_myreview",
    "mychart": "ma_mychart",
    "chartonline": "ma_chartonline",
    "danall": "ma_danall",
    "chartlist": "ma_chartlist",
    "addfriend": "ma_addfriend",
    "like": "ma_like",
    "createchart": "ma_createchart",
    "donate": "ma_donate",
    "chartpromote": "ma_chartpromote",
    "settype": "ma_settype",
    "updatehash": "ma_updatehash",
    "createsong": "ma_createsong",
    "addcomment": "ma_addcomment",
    "delcomment": "ma_delcomment",
    "addreview": "ma_addreview",
    "reviewaction": "ma_reviewaction",
    "reviewcharts": "ma_reviewcharts",
    "reviewreply": "ma_reviewreply",
    "delreview": "ma_delreview",
    "reviewstatus": "ma_reviewstatus",
    "delaccount": "ma_delaccount",
    "renew": "ma_renew",
    "storeinfo": "ma_storeinfo",
    "searchstore": "ma_searchstore",
    "download": "ma_download",
    "friendstore": "ma_friendstore",
    "mute": "ma_mute",
    "skincheck": "ma_skincheck",
    "buyskin": "ma_buyskin",
    "slot": "ma_slot",
}

MA_HELP = """MalodyV Bot (Discord / Telegram)
ma profile/search/rank/dan/danall/friend
ma achieve/items/marlo/activity/puzzle
ma chart/song/wiki/chartonline
ma store/choice/promote/skin/download
ma news/quest/event/storeinfo
ma global/chartrank/eventrank
ma comment/review/reviewqueue/myreview
ma mychart/chartlist/searchstore/friendstore
ma addfriend/like/addcomment/delcomment
ma createchart/createsong/chartpromote/settype/updatehash
ma addreview/reviewreply/delreview/reviewstatus
ma logout/renew/delaccount/mute/slot/skincheck/buyskin
/login | /mb | /mm"""


def _handler_module(name: str):
    return importlib.import_module(f"{HANDLER_PACKAGE}.{name}")


ma_command = on_command(
    "ma",
    aliases={"MA", "Ma", "malody"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@ma_command.handle()
async def handle_ma(bot: Bot, event: Event, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    portable_bot = PlatformBot(bot, event)
    portable_event = PlatformEvent(bot, event)
    if not text:
        await portable_bot.send(portable_event, MA_HELP)
        return

    parts = text.split(maxsplit=1)
    subcommand = parts[0].lower()
    subargs = parts[1] if len(parts) > 1 else ""
    module_name = MA_SUBCOMMANDS.get(subcommand)
    if not module_name:
        await portable_bot.send(
            portable_event, f"未知命令: {subcommand}，输入 /ma 查看命令列表"
        )
        return

    try:
        module = _handler_module(module_name)
        await module.handle(portable_bot, portable_event, subargs)
    except Exception as exc:
        logger.opt(exception=exc).error(
            "Cross-platform MalodyV command failed: ma {}", subcommand
        )
        await portable_bot.send(portable_event, "命令执行失败，请检查后台日志。")


mm_command = on_command(
    "mm",
    aliases={"MM"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@mm_command.handle()
async def handle_mm(args: Message = CommandArg()):
    module = _handler_module("mm_handler")
    try:
        result = module.process_mm(args.extract_plain_text().strip())
    except ValueError as exc:
        await mm_command.finish(str(exc))
    except Exception as exc:
        logger.opt(exception=exc).error("Cross-platform MM calculation failed")
        await mm_command.finish("计算失败，请检查参数。")
    await mm_command.finish(result)


best_command = on_command(
    "mb",
    aliases={"mmbest", "mmb", "mabest"},
    priority=10,
    block=True,
    rule=foreign_adapter,
)


@best_command.handle()
async def handle_best(bot: Bot, event: Event, args: Message = CommandArg()):
    module = _handler_module("mmbest_handler")
    await module.process_best(
        PlatformBot(bot, event),
        PlatformEvent(bot, event),
        args.extract_plain_text().strip(),
    )


login_command = on_command(
    "login",
    aliases={"登录"},
    priority=10,
    block=True,
    rule=foreign_adapter,
)


@login_command.handle()
async def handle_login(bot: Bot, event: Event, args: Message = CommandArg()):
    module = _handler_module("login_handler")
    await module.process_login(
        PlatformBot(bot, event),
        PlatformEvent(bot, event),
        args.extract_plain_text().strip(),
    )


async def _foreign_private(bot: Bot, event: Event) -> bool:
    return bot.adapter.get_name() in {"Discord", "Telegram"} and not is_group_event(
        event
    )


password_listener = on_message(
    rule=Rule(_foreign_private),
    priority=9,
    block=False,
)


@password_listener.handle()
async def handle_pending_password(bot: Bot, event: Event):
    module = _handler_module("login_handler")
    portable_event = PlatformEvent(bot, event)
    identity = str(portable_event.get_user_id())
    pending = module.pending_logins.get(identity)
    if not pending:
        return
    pending["task"].cancel()
    await module.handle_password(
        PlatformBot(bot, event),
        portable_event,
        identity,
        event.get_plaintext().strip(),
    )
