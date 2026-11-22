from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path

from nonebot import logger, on_command, on_message
from nonebot.adapters import Bot, Event, Message
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message as OneBotMessage,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.event import Reply, Sender
from nonebot.params import CommandArg

from . import foreign_adapter
from .framework import PlatformBot, is_group_event
from .media import download_media, incoming_media

try:
    from ..baka_chat import _handle_command as original_baka_command
    from ..baka_chat import service
except ImportError:
    original_baka_command = None
    service = None


MEDIA_CACHE = Path("data/multiplatform/incoming")
MEDIA_CACHE.mkdir(parents=True, exist_ok=True)


def _integer_id(value) -> int:
    try:
        return int(value)
    except Exception:
        return int.from_bytes(
            hashlib.blake2b(str(value).encode(), digest_size=8).digest(), "big"
        ) & 0x7FFFFFFFFFFFFFFF


def _sender(event: Event) -> Sender:
    source = getattr(event, "author", None) or getattr(event, "from_", None)
    user_id = _integer_id(event.get_user_id())
    nickname = (
        getattr(source, "global_name", None)
        or getattr(source, "username", None)
        or getattr(source, "first_name", None)
        or str(user_id)
    )
    card = getattr(getattr(event, "member", None), "nick", None) or nickname
    return Sender(
        user_id=user_id,
        nickname=str(nickname),
        card=str(card),
        role="member",
    )


async def _media_source(bot: Bot, item) -> str:
    if item.url:
        return item.url
    digest = hashlib.sha256(
        f"{bot.adapter.get_name()}:{item.file_id}:{item.name}".encode()
    ).hexdigest()
    target = MEDIA_CACHE / f"{digest}{Path(item.name).suffix or '.bin'}"
    if not target.exists():
        try:
            await download_media(bot, item, target)
        except Exception:
            logger.exception("Failed to cache cross-platform Baka Chat media")
    return target.resolve().as_uri() if target.exists() else ""


async def _message(bot: Bot, event: Event, *, include_media: bool = True) -> OneBotMessage:
    result = OneBotMessage()
    text = event.get_plaintext()
    if is_group_event(event) and event.is_tome():
        result += MessageSegment.at(_integer_id(bot.self_id))
        result += MessageSegment.text(" ")
    if text:
        result += MessageSegment.text(text)
    if not include_media:
        return result
    for item in incoming_media(event, include_reply=False):
        source = await _media_source(bot, item)
        if item.kind == "image" and source:
            result += MessageSegment.image(source)
        elif item.kind == "video" and source:
            result += MessageSegment.video(source)
        elif item.kind == "audio" and source:
            result += MessageSegment.record(source)
        else:
            result += MessageSegment(
                "file",
                {
                    "name": item.name,
                    "file": source or item.file_id or "",
                    "file_id": item.file_id or "",
                    "url": source,
                },
            )
    return result


async def _reply(bot: Bot, event: Event) -> Reply | None:
    native = getattr(event, "reply_to_message", None) or getattr(
        event, "referenced_message", None
    )
    if native is None:
        return None
    try:
        reply_message = await _message(bot, native, include_media=False)
        reply_sender = _sender(native)
        message_id = _integer_id(
            getattr(native, "message_id", getattr(native, "id", 0))
        )
        return Reply(
            time=int(time.time()),
            message_type="group" if is_group_event(event) else "private",
            message_id=message_id,
            real_id=message_id,
            sender=reply_sender,
            message=reply_message,
        )
    except Exception:
        return None


async def as_onebot_event(bot: Bot, event: Event):
    message = await _message(bot, event)
    sender = _sender(event)
    message_id = _integer_id(
        getattr(event, "message_id", getattr(event, "id", 0))
    )
    timestamp = getattr(event, "date", None)
    if timestamp is None:
        value = getattr(event, "timestamp", None)
        timestamp = int(value.timestamp()) if isinstance(value, datetime) else int(time.time())
    common = {
        "time": int(timestamp),
        "self_id": _integer_id(bot.self_id),
        "post_type": "message",
        "sub_type": "normal" if is_group_event(event) else "friend",
        "user_id": _integer_id(event.get_user_id()),
        "message_id": message_id,
        "message": message,
        "original_message": message,
        "raw_message": event.get_plaintext(),
        "font": 0,
        "sender": sender,
        "to_me": event.is_tome(),
        "reply": await _reply(bot, event),
    }
    if is_group_event(event):
        chat = getattr(event, "chat", None)
        group_id = getattr(chat, "id", None) or getattr(event, "channel_id", None)
        return GroupMessageEvent(
            **common,
            message_type="group",
            group_id=_integer_id(group_id),
        )
    return PrivateMessageEvent(**common, message_type="private")


baka_command = on_command(
    "baka",
    aliases={"琪露诺管理", "baka管理"},
    priority=4,
    block=True,
    rule=foreign_adapter,
)


@baka_command.handle()
async def handle_baka_command(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    if original_baka_command is None:
        await baka_command.finish("Baka Chat 模块不可用。")
    synthetic = await as_onebot_event(bot, event)
    await original_baka_command(PlatformBot(bot, event), synthetic, args)


baka_chat = on_message(
    priority=98,
    block=False,
    rule=foreign_adapter,
)


@baka_chat.handle()
async def handle_baka_chat(bot: Bot, event: Event):
    if service is None:
        return
    try:
        synthetic = await as_onebot_event(bot, event)
        await service.handle_event(PlatformBot(bot, event), synthetic)
    except Exception as exc:
        logger.opt(exception=exc).error(
            "Cross-platform Baka Chat event handling failed"
        )
