"""Automatic help once per message, and persistent group-wide TD opt-out."""
from __future__ import annotations

import asyncio
from pathlib import Path

from nonebot import get_driver, logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.message import event_preprocessor
from nonebot.rule import Rule
from nonebot.typing import T_State

from .preferences import Preferences

HELP_TEXT = 'Baka666bot使用帮助:malody.top/bakahelp'
GROUP_TIP = HELP_TEXT + '\n发送 TD 可关闭本群自动帮助提示。'
PRIVATE_TIP = HELP_TEXT + '\n发送 TD 可关闭自动帮助提示。'
preferences = Preferences(Path(getattr(get_driver().config, 'bakahelp_preferences_path',
                                       'data/Bakahelp/preferences.sqlite3')))


def scope_key(bot: Bot, event: Event) -> str:
    native = vars(bot).get('native_bot', bot)
    adapter = native.adapter.get_name()
    group = getattr(event, 'group_id', None)
    return f'{adapter}:group:{group}' if group is not None else f'{adapter}:user:{event.get_user_id()}'


def is_td(event: Event) -> bool:
    try:
        text = event.get_plaintext().strip().casefold()
    except Exception:
        return False
    prefixes = set(get_driver().config.command_start) | {'', '/'}
    return text in {prefix + 'td' for prefix in prefixes}


@event_preprocessor
async def prepare_help(bot: Bot, event: Event, state: T_State):
    if not isinstance(event, MessageEvent):
        return
    # NoneBot copies state shallowly for each matcher; share the once-only flag.
    state['_baka_message'] = {'help_lock': asyncio.Lock(), 'help_sent': False}
    if is_td(event):
        # Every bot observes TD before free_egg's highest-priority matcher.
        await asyncio.to_thread(preferences.disable, scope_key(bot, event))
        state['_baka_message']['td'] = True


async def send_help(bot: Bot, event: Event, state: T_State, *, explicit: bool = False):
    context = state['_baka_message']
    async with context['help_lock']:
        if context['help_sent'] or context.get('td'):
            return
        if not explicit:
            try:
                if await asyncio.to_thread(preferences.disabled, scope_key(bot, event)):
                    return
            except Exception:
                logger.warning('Bakahelp: preferences unavailable; automatic notice skipped')
                return
        context['help_sent'] = True
        text = GROUP_TIP if getattr(event, 'group_id', None) is not None else PRIVATE_TIP
        try:
            await bot.send(event, text)
        except Exception:
            logger.warning('Bakahelp: sending help failed; command processing continues')


def slash_message(event: Event) -> bool:
    if not isinstance(event, MessageEvent) or is_td(event):
        return False
    return event.get_plaintext().lstrip().startswith('/')


slash_notice = on_message(rule=Rule(slash_message), priority=-10, block=False)
unsubscribe = on_message(rule=Rule(is_td), priority=-20, block=True)


@slash_notice.handle()
async def handle_slash(bot: Bot, event: Event, state: T_State):
    await send_help(bot, event, state)


@unsubscribe.handle()
async def handle_td(bot: Bot, event: Event):
    await bot.send(event, '已关闭本群自动帮助提示，发送 help 仍可查看帮助。'
                   if getattr(event, 'group_id', None) is not None
                   else '已关闭自动帮助提示，发送 help 仍可查看帮助。')

