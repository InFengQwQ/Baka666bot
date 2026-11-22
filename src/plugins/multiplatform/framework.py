from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from nonebot.adapters import Bot, Event, Message as GenericMessage
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg import (
    AtAll,
    Audio,
    File,
    Image,
    Reply,
    Text,
    Video,
)

from nonebot.adapters.onebot.v11 import (
    Message as OneBotMessage,
    MessageSegment as OneBotMessageSegment,
)


def adapter_name(bot: Bot) -> str:
    return bot.adapter.get_name()


def is_foreign_bot(bot: Bot) -> bool:
    return adapter_name(bot) in {"Discord", "Telegram"}


def _native_user_id(event: Event) -> str:
    try:
        return str(event.get_user_id())
    except Exception:
        for name in ("user_id", "author_id", "from_"):
            value = getattr(event, name, None)
            if value is not None:
                return str(getattr(value, "id", value))
    return "unknown"


def _scope_id(event: Event) -> str:
    chat = getattr(event, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        return str(chat.id)
    channel_id = getattr(event, "channel_id", None)
    if channel_id is not None:
        return str(channel_id)
    return _native_user_id(event)


def is_group_event(event: Event) -> bool:
    chat = getattr(event, "chat", None)
    if chat is not None:
        return str(getattr(chat, "type", "private")) in {
            "group",
            "supergroup",
            "channel",
        }
    try:
        from nonebot.adapters.discord.event import GuildMessageCreateEvent

        return isinstance(event, GuildMessageCreateEvent)
    except Exception:
        return False


def platform_user_id(bot: Bot, event: Event) -> str:
    return f"{adapter_name(bot).lower()}:{_native_user_id(event)}"


def _path_from_uri(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


def _media_kwargs(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        return {"raw": value}
    if isinstance(value, os.PathLike):
        return {"path": Path(value)}
    if not isinstance(value, str):
        return {"raw": bytes(value)}
    if value.startswith("base64://"):
        try:
            return {"raw": base64.b64decode(value[9:])}
        except Exception:
            return {}
    if value.startswith(("http://", "https://")):
        return {"url": value}
    if path := _path_from_uri(value):
        return {"path": path}
    if Path(value).is_file():
        return {"path": Path(value)}
    return {"id": value}


def _segment_to_unimessage(segment: OneBotMessageSegment) -> UniMessage:
    data = dict(segment.data)
    kind = segment.type

    if kind == "text":
        return UniMessage(Text(str(data.get("text", ""))))
    if kind in {"image", "mface"}:
        source = data.get("file") or data.get("url") or ""
        return UniMessage(Image(name="image.png", **_media_kwargs(source)))
    if kind == "video":
        source = data.get("file") or data.get("url") or ""
        return UniMessage(Video(name="video.mp4", **_media_kwargs(source)))
    if kind == "record":
        source = data.get("file") or data.get("url") or ""
        return UniMessage(Audio(name="audio.mp3", **_media_kwargs(source)))
    if kind == "file":
        name = str(data.get("name") or data.get("filename") or "file.bin")
        source = data.get("file") or data.get("url") or ""
        return UniMessage(File(name=name, **_media_kwargs(source)))
    if kind == "at":
        target = str(data.get("qq", ""))
        if target == "all":
            return UniMessage(AtAll())
        return UniMessage.at(target)
    if kind == "reply":
        return UniMessage(Reply(str(data.get("id", ""))))
    if kind in {"face", "json", "xml", "forward", "node"}:
        labels = {
            "face": "[表情]",
            "json": "[卡片消息]",
            "xml": "[XML消息]",
            "forward": "[合并转发]",
            "node": "[转发消息]",
        }
        return UniMessage(Text(labels[kind]))
    return UniMessage(Text(f"[{kind}]"))


def onebot_to_unimessage(message: Any) -> UniMessage:
    if isinstance(message, OneBotMessageSegment):
        return _segment_to_unimessage(message)
    if isinstance(message, OneBotMessage):
        result = UniMessage()
        for segment in message:
            result += _segment_to_unimessage(segment)
        return result
    if isinstance(message, GenericMessage):
        result = UniMessage()
        for segment in message:
            if isinstance(segment, OneBotMessageSegment):
                result += _segment_to_unimessage(segment)
        return result
    return UniMessage.text(str(message))


class PlatformEvent:
    """OneBot-shaped view used only when calling existing plugin functions."""

    def __init__(self, bot: Bot, event: Event):
        self.bot = bot
        self.native_event = event
        self.user_id = platform_user_id(bot, event)
        self.group_id = _scope_id(event)
        self.message_type = "group" if is_group_event(event) else "private"
        self.message_id = getattr(event, "message_id", getattr(event, "id", "0"))
        self.time = getattr(event, "date", 0)
        self.sender = getattr(event, "author", getattr(event, "from_", None))
        self.reply = self._make_reply()

    def _make_reply(self):
        native_reply = getattr(self.native_event, "reply", None)
        if native_reply is None:
            native_reply = getattr(self.native_event, "reply_to_message", None)
        if native_reply is None:
            return None
        return type(
            "PlatformReply",
            (),
            {
                "message_id": getattr(
                    native_reply, "message_id", getattr(native_reply, "id", "0")
                ),
                "message": getattr(native_reply, "message", GenericMessage()),
                "sender": getattr(
                    native_reply, "author", getattr(native_reply, "from_", None)
                ),
            },
        )()

    def get_user_id(self) -> str:
        return self.user_id

    def get_session_id(self) -> str:
        return f"{self.message_type}:{self.group_id}:{self.user_id}"

    def get_message(self):
        return self.native_event.get_message()

    def get_plaintext(self) -> str:
        return self.native_event.get_plaintext()

    def get_event_description(self) -> str:
        return self.native_event.get_event_description()

    def is_tome(self) -> bool:
        return self.native_event.is_tome()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.native_event, name)


class PlatformBot:
    """Bot facade for existing plugin handlers.

    It delegates all transport work to the official adapter Bot and only
    translates legacy OneBot message segments at the plugin boundary.
    """

    def __init__(self, bot: Bot, event: Event):
        self.native_bot = bot
        self.native_event = event
        self.self_id = bot.self_id
        self.adapter = bot.adapter
        self.type = bot.type

    async def send(self, event: PlatformEvent | Event, message: Any, **kwargs: Any):
        if isinstance(event, PlatformEvent):
            target = event.native_event
        elif event.__class__.__module__.startswith("nonebot.adapters.onebot"):
            target = self.native_event
        else:
            target = event
        reply_to = bool(kwargs.pop("reply_message", False))
        at_sender = bool(kwargs.pop("at_sender", False))
        unified = (
            UniMessage.text(message)
            if isinstance(message, str)
            else message
            if isinstance(message, UniMessage)
            else onebot_to_unimessage(message)
        )
        return await unified.send(
            target=target,
            bot=self.native_bot,
            reply_to=reply_to,
            at_sender=at_sender,
            **kwargs,
        )

    async def send_group_msg(self, *, message: Any, **kwargs: Any):
        return await self.send(self.native_event, message, **kwargs)

    async def send_private_msg(self, *, message: Any, **kwargs: Any):
        return await self.send(self.native_event, message, **kwargs)

    async def upload_group_file(self, *, file: str, name: str | None = None, **kwargs: Any):
        return await UniMessage.file(path=file, name=name or Path(file).name).send(
            target=self.native_event, bot=self.native_bot
        )

    async def upload_private_file(
        self, *, file: str, name: str | None = None, **kwargs: Any
    ):
        return await UniMessage.file(path=file, name=name or Path(file).name).send(
            target=self.native_event, bot=self.native_bot
        )

    def _chat_id(self) -> str:
        chat = getattr(self.native_event, "chat", None)
        if chat is not None:
            return str(chat.id)
        return str(getattr(self.native_event, "channel_id", ""))

    def _guild_id(self) -> str:
        return str(getattr(self.native_event, "guild_id", ""))

    async def get_group_member_list(self, **kwargs: Any):
        if adapter_name(self.native_bot) == "Discord":
            members = await self.native_bot.list_guild_members(
                guild_id=self._guild_id(), limit=1000
            )
            result = []
            for member in members:
                user = getattr(member, "user", None)
                if user is None:
                    continue
                result.append(
                    {
                        "user_id": int(user.id),
                        "nickname": user.username,
                        "card": getattr(member, "nick", None) or user.username,
                        "role": "member",
                    }
                )
            return result
        admins = await self.native_bot.get_chat_administrators(chat_id=self._chat_id())
        return [
            {
                "user_id": int(item.user.id),
                "nickname": item.user.first_name,
                "card": getattr(item, "custom_title", None) or item.user.first_name,
                "role": "owner" if item.status == "creator" else "admin",
            }
            for item in admins
        ]

    async def get_group_member_info(self, *, user_id: Any, **kwargs: Any):
        if adapter_name(self.native_bot) == "Discord":
            member = await self.native_bot.get_guild_member(
                guild_id=self._guild_id(), user_id=int(user_id)
            )
            user = getattr(member, "user", None)
            return {
                "user_id": int(user_id),
                "nickname": getattr(user, "username", str(user_id)),
                "card": getattr(member, "nick", None)
                or getattr(user, "username", str(user_id)),
                "role": "member",
            }
        member = await self.native_bot.get_chat_member(
            chat_id=self._chat_id(), user_id=int(user_id)
        )
        return {
            "user_id": int(user_id),
            "nickname": member.user.first_name,
            "card": getattr(member, "custom_title", None) or member.user.first_name,
            "role": "owner"
            if member.status == "creator"
            else "admin"
            if member.status == "administrator"
            else "member",
        }

    async def set_group_ban(
        self, *, user_id: Any, duration: int = 60, **kwargs: Any
    ):
        if adapter_name(self.native_bot) == "Discord":
            until = (
                datetime.now(timezone.utc) + timedelta(seconds=max(duration, 0))
                if duration > 0
                else None
            )
            return await self.native_bot.modify_guild_member(
                guild_id=self._guild_id(),
                user_id=int(user_id),
                communication_disabled_until=until,
            )
        from nonebot.adapters.telegram.model import ChatPermissions

        permissions = ChatPermissions(
            can_send_messages=duration <= 0,
            can_send_audios=duration <= 0,
            can_send_documents=duration <= 0,
            can_send_photos=duration <= 0,
            can_send_videos=duration <= 0,
            can_send_video_notes=duration <= 0,
            can_send_voice_notes=duration <= 0,
            can_send_polls=duration <= 0,
            can_send_other_messages=duration <= 0,
        )
        return await self.native_bot.restrict_chat_member(
            chat_id=self._chat_id(),
            user_id=int(user_id),
            permissions=permissions,
            until_date=int(time.time()) + duration if duration > 0 else None,
        )

    async def set_group_kick(
        self, *, user_id: Any, reject_add_request: bool = False, **kwargs: Any
    ):
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.remove_guild_member(
                guild_id=self._guild_id(), user_id=int(user_id)
            )
        result = await self.native_bot.ban_chat_member(
            chat_id=self._chat_id(), user_id=int(user_id)
        )
        if not reject_add_request:
            await self.native_bot.unban_chat_member(
                chat_id=self._chat_id(), user_id=int(user_id)
            )
        return result

    async def set_group_card(self, *, user_id: Any, card: str = "", **kwargs: Any):
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.modify_guild_member(
                guild_id=self._guild_id(),
                user_id=int(user_id),
                nick=card or None,
            )
        return await self.native_bot.set_chat_administrator_custom_title(
            chat_id=self._chat_id(),
            user_id=int(user_id),
            custom_title=card[:16],
        )

    async def set_group_admin(
        self, *, user_id: Any, enable: bool = True, **kwargs: Any
    ):
        if adapter_name(self.native_bot) == "Telegram":
            return await self.native_bot.promote_chat_member(
                chat_id=self._chat_id(),
                user_id=int(user_id),
                can_manage_chat=enable,
                can_delete_messages=enable,
                can_restrict_members=enable,
                can_invite_users=enable,
                can_pin_messages=enable,
                can_manage_topics=enable,
            )
        return {"status": "unsupported", "reason": "Discord requires a configured role"}

    async def delete_msg(self, *, message_id: Any, **kwargs: Any):
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.delete_message(
                channel_id=self._chat_id(), message_id=int(message_id)
            )
        return await self.native_bot.delete_message(
            chat_id=self._chat_id(), message_id=int(message_id)
        )

    async def _react(self, emoji: str = "👍"):
        message_id = int(getattr(self.native_event, "message_id", getattr(self.native_event, "id", 0)))
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.create_reaction(
                channel_id=self._chat_id(), message_id=message_id, emoji=emoji
            )
        from nonebot.adapters.telegram.model import ReactionTypeEmoji

        return await self.native_bot.set_message_reaction(
            chat_id=self._chat_id(),
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )

    async def call_api(self, api: str, **data: Any):
        if api in {"send_group_forward_msg", "send_private_forward_msg"}:
            nodes = data.get("messages") or data.get("message") or []
            for node in nodes:
                content = node.get("content") if isinstance(node, dict) else node
                await self.send(self.native_event, content)
            return {"status": "ok"}
        if api in {"send_poke", "send_like"}:
            return await self._react("👋" if api == "send_poke" else "👍")
        if api == "delete_msg":
            return await self.delete_msg(**data)
        if api == "set_group_ban":
            return await self.set_group_ban(**data)
        if api == "set_group_kick":
            return await self.set_group_kick(**data)
        if api == "set_group_card":
            return await self.set_group_card(**data)
        if api == "set_group_admin":
            return await self.set_group_admin(
                user_id=data.get("user_id"), enable=data.get("enable", True)
            )
        if api in {
            "set_group_special_title",
            "set_group_whole_ban",
            "set_group_anonymous",
            "set_group_anonymous_ban",
            "set_group_name",
            "set_group_portrait",
            "set_group_add_request",
        }:
            return {"status": "unsupported", "api": api}
        return await self.native_bot.call_api(api, **data)

    def __getattr__(self, name: str):
        return getattr(self.native_bot, name)
