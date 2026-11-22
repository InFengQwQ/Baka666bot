from __future__ import annotations

from nonebot import on_message
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule

from .framework import PlatformBot, is_group_event


EGG = "🥚"
MAX_BYTES = 60


def _nickname(event: Event) -> str:
    author = getattr(event, "author", None) or getattr(event, "from_", None)
    member = getattr(event, "member", None)
    return str(
        getattr(member, "nick", None)
        or getattr(author, "global_name", None)
        or getattr(author, "username", None)
        or getattr(author, "first_name", None)
        or ""
    )


def _with_egg(value: str) -> str:
    if value.endswith(EGG):
        return value
    while value and len((value + EGG).encode("utf-8")) > MAX_BYTES:
        value = value[:-1]
    return value + EGG


def _rule(bot: Bot, event: Event) -> bool:
    return (
        bot.adapter.get_name() in {"Discord", "Telegram"}
        and is_group_event(event)
        and event.get_plaintext().strip().startswith("/")
    )


matcher = on_message(rule=Rule(_rule), priority=0, block=False)


@matcher.handle()
async def handle_free_egg(bot: Bot, event: Event):
    facade = PlatformBot(bot, event)
    name = _nickname(event)
    if name:
        try:
            await facade.set_group_card(
                user_id=event.get_user_id(), card=_with_egg(name)
            )
        except Exception:
            pass
    try:
        await facade._react(EGG)
    except Exception:
        pass
