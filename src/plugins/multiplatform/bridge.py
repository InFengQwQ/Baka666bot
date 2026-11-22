from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nonebot import get_driver
from nonebot.adapters import Bot, Event, Message as NativeMessage
from nonebot.adapters.onebot.v11 import (
    Bot as OneBotBot,
    GroupMessageEvent,
    Message as OneBotMessage,
    MessageEvent as OneBotMessageEvent,
    MessageSegment as OneBotMessageSegment,
    PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.event import Reply, Sender
from nonebot.exception import IgnoredException
from nonebot.log import logger
from nonebot.message import event_preprocessor, handle_event
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg import Target

from .framework import adapter_name, is_group_event, onebot_to_unimessage


SUPPORTED_ADAPTERS = {"Discord", "Telegram"}


@dataclass
class ForeignFile:
    file_id: str
    name: str
    url: str = ""


def _as_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _user_id(event: Event) -> int:
    try:
        return _as_int(event.get_user_id())
    except (AttributeError, ValueError):
        user = getattr(event, "author", None) or getattr(event, "from_", None)
        return _as_int(getattr(user, "id", 0))


def _group_id(event: Event) -> int:
    chat = getattr(event, "chat", None)
    if chat is not None:
        return _as_int(getattr(chat, "id", 0))
    return _as_int(getattr(event, "channel_id", 0))


def _message_id(event: Any) -> int:
    return _as_int(getattr(event, "message_id", getattr(event, "id", 0)))


def _event_time(event: Any) -> int:
    value = getattr(event, "date", getattr(event, "timestamp", None))
    if isinstance(value, datetime):
        return int(value.timestamp())
    return _as_int(value, int(time.time()))


def _native_sender(event: Any) -> Any:
    return getattr(event, "author", None) or getattr(event, "from_", None)


def _sender(event: Any) -> Sender:
    user = _native_sender(event)
    member = getattr(event, "member", None)
    nickname = (
        getattr(member, "nick", None)
        or getattr(user, "global_name", None)
        or getattr(user, "username", None)
        or " ".join(
            item
            for item in (
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            )
            if item
        )
        or str(getattr(user, "id", "unknown"))
    )
    return Sender(
        user_id=_as_int(getattr(user, "id", 0)),
        nickname=str(nickname),
        card=str(getattr(member, "nick", None) or nickname),
        role="member",
    )


def _is_bot_message(event: Event) -> bool:
    user = _native_sender(event)
    return bool(getattr(user, "bot", False) or getattr(user, "is_bot", False))


def _discord_file(segment: Any) -> ForeignFile | None:
    if getattr(segment, "type", "") != "attachment":
        return None
    data = segment.data
    attachment = data.get("attachment")
    name = str(getattr(attachment, "filename", None) or "file.bin")
    url = str(data.get("url") or data.get("proxy_url") or "")
    return ForeignFile(file_id=url or name, name=name, url=url)


def _telegram_raw_message(event: Event, *, reply: bool) -> Any:
    update = getattr(event, "telegram_model", None)
    if update is None:
        return None
    raw = (
        getattr(update, "message", None)
        or getattr(update, "channel_post", None)
        or getattr(update, "edited_message", None)
        or getattr(update, "edited_channel_post", None)
    )
    if reply and raw is not None:
        return getattr(raw, "reply_to_message", None)
    return raw


def _telegram_files(event: Event, *, reply: bool) -> dict[str, ForeignFile]:
    raw = _telegram_raw_message(event, reply=reply)
    result: dict[str, ForeignFile] = {}
    if raw is None:
        return result

    document = getattr(raw, "document", None)
    if document is not None:
        file_id = str(document.file_id)
        result[file_id] = ForeignFile(
            file_id=file_id,
            name=str(getattr(document, "file_name", None) or "file.bin"),
        )

    defaults = {
        "audio": "audio.mp3",
        "video": "video.mp4",
        "animation": "animation.mp4",
        "voice": "voice.ogg",
        "sticker": "sticker.webp",
        "video_note": "video.mp4",
    }
    for field, default_name in defaults.items():
        item = getattr(raw, field, None)
        if item is None:
            continue
        file_id = str(item.file_id)
        result[file_id] = ForeignFile(
            file_id=file_id,
            name=str(getattr(item, "file_name", None) or default_name),
        )

    photos = getattr(raw, "photo", None)
    if photos:
        file_id = str(photos[-1].file_id)
        result[file_id] = ForeignFile(file_id=file_id, name="image.jpg")
    return result


def _file_segment(file: ForeignFile, kind: str) -> OneBotMessageSegment:
    data = {
        "file": file.name,
        "file_id": file.file_id,
        "url": file.url,
        "name": file.name,
        "filename": file.name,
        "file_name": file.name,
    }
    if kind == "image":
        return OneBotMessageSegment.image(file.url or file.file_id)
    if kind == "video":
        return OneBotMessageSegment.video(file.url or file.file_id)
    if kind in {"audio", "voice"}:
        return OneBotMessageSegment.record(file.url or file.file_id)
    return OneBotMessageSegment(type="file", data=data)


def native_message_to_onebot(
    event: Event,
    message: NativeMessage,
    *,
    reply: bool = False,
) -> tuple[OneBotMessage, dict[str, ForeignFile]]:
    result = OneBotMessage()
    files: dict[str, ForeignFile] = {}
    telegram_files = _telegram_files(event, reply=reply)

    for segment in message:
        kind = segment.type
        data = segment.data
        if segment.is_text():
            if kind == "text_mention":
                user = data.get("user")
                if user is not None:
                    result.append(OneBotMessageSegment.at(getattr(user, "id", 0)))
                    continue
            result.append(OneBotMessageSegment.text(str(data.get("text", ""))))
            continue

        if kind == "mention_user":
            result.append(OneBotMessageSegment.at(data.get("user_id", 0)))
            continue
        if kind == "mention_everyone":
            result.append(OneBotMessageSegment.at("all"))
            continue

        discord_file = _discord_file(segment)
        if discord_file is not None:
            files[discord_file.file_id] = discord_file
            files[discord_file.name] = discord_file
            suffix = Path(discord_file.name).suffix.lower()
            media_kind = (
                "image"
                if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                else "video"
                if suffix in {".mp4", ".mov", ".webm", ".mkv"}
                else "audio"
                if suffix in {".mp3", ".ogg", ".wav", ".flac", ".m4a"}
                else "file"
            )
            result.append(_file_segment(discord_file, media_kind))
            continue

        if kind in {
            "photo",
            "document",
            "video",
            "animation",
            "audio",
            "voice",
            "sticker",
            "video_note",
        }:
            file_id = str(data.get("file") or "")
            file = telegram_files.get(
                file_id,
                ForeignFile(
                    file_id=file_id,
                    name={
                        "photo": "image.jpg",
                        "document": "file.bin",
                        "video": "video.mp4",
                        "animation": "animation.mp4",
                        "audio": "audio.mp3",
                        "voice": "voice.ogg",
                        "sticker": "sticker.webp",
                        "video_note": "video.mp4",
                    }[kind],
                ),
            )
            files[file.file_id] = file
            files[file.name] = file
            media_kind = (
                "image"
                if kind in {"photo", "sticker"}
                else "video"
                if kind in {"video", "animation", "video_note"}
                else "audio"
                if kind in {"audio", "voice"}
                else "file"
            )
            result.append(_file_segment(file, media_kind))
            continue

        if kind == "reply":
            result.append(OneBotMessageSegment.reply(_as_int(data.get("message_id"))))
            continue

        result.append(OneBotMessageSegment.text(f"[{kind}]"))
    return result, files


def _reply_event(event: Event) -> Any:
    for name in ("reply_to_message", "reply", "referenced_message"):
        value = getattr(event, name, None)
        if value is None:
            continue
        if value.__class__.__name__ == "_Unset":
            continue
        if isinstance(value, type) and value.__name__ == "UNSET":
            continue
        return value
    return None


def _reply_message(event: Event, native_reply: Any) -> NativeMessage:
    if hasattr(native_reply, "get_message"):
        return native_reply.get_message()
    if adapter_name_from_event(event) == "Discord":
        from nonebot.adapters.discord.message import Message

        return Message.from_guild_message(native_reply)
    return NativeMessage()


def adapter_name_from_event(event: Event) -> str:
    module = event.__class__.__module__
    if ".discord." in module:
        return "Discord"
    if ".telegram." in module:
        return "Telegram"
    return ""


def build_onebot_event(
    bot: Bot,
    event: Event,
) -> tuple[OneBotMessageEvent, dict[str, ForeignFile]]:
    message, files = native_message_to_onebot(event, event.get_message())
    native_reply = _reply_event(event)
    reply = None
    if native_reply is not None:
        reply_message, reply_files = native_message_to_onebot(
            event,
            _reply_message(event, native_reply),
            reply=True,
        )
        files.update(reply_files)
        reply = Reply(
            time=_event_time(native_reply),
            message_type="group" if is_group_event(event) else "private",
            message_id=_message_id(native_reply),
            real_id=_message_id(native_reply),
            sender=_sender(native_reply),
            message=reply_message,
        )

    common = {
        "time": _event_time(event),
        "self_id": _as_int(bot.self_id),
        "post_type": "message",
        "sub_type": "normal",
        "user_id": _user_id(event),
        "message_id": _message_id(event),
        "message": message,
        "original_message": OneBotMessage(message),
        "raw_message": message.extract_plain_text(),
        "font": 0,
        "sender": _sender(event),
        "to_me": bool(event.is_tome()),
        "reply": reply,
    }
    if is_group_event(event):
        return (
            GroupMessageEvent(
                message_type="group",
                group_id=_group_id(event),
                **common,
            ),
            files,
        )
    return PrivateMessageEvent(message_type="private", **common), files


class OneBotCompatBot(OneBotBot):
    def __init__(
        self,
        native_bot: Bot,
        native_event: Event,
        files: dict[str, ForeignFile],
    ):
        onebot_adapter = get_driver()._adapters["OneBot V11"]
        super().__init__(onebot_adapter, str(native_bot.self_id))
        self.native_bot = native_bot
        self.native_event = native_event
        self.files = files

    def _current_target(self, private: bool) -> int:
        return _user_id(self.native_event) if private else _group_id(self.native_event)

    def _target(self, target_id: Any, private: bool) -> Event | Target:
        if _as_int(target_id) == self._current_target(private):
            return self.native_event
        name = adapter_name(self.native_bot)
        return Target(
            str(target_id),
            channel=name == "Discord",
            private=private,
            adapter=name,
            self_id=self.native_bot.self_id,
        )

    async def _send(
        self,
        message: Any,
        *,
        target: Event | Target,
        at_sender: bool = False,
        reply_message: bool = False,
    ) -> Any:
        unified = (
            message
            if isinstance(message, UniMessage)
            else UniMessage.text(message)
            if isinstance(message, str)
            else onebot_to_unimessage(message)
        )
        return await unified.send(
            target=target,
            bot=self.native_bot,
            at_sender=at_sender,
            reply_to=reply_message,
        )

    async def send(
        self,
        event: Event,
        message: Any,
        **kwargs: Any,
    ) -> Any:
        return await self._send(
            message,
            target=self.native_event,
            at_sender=bool(kwargs.get("at_sender", False)),
            reply_message=bool(kwargs.get("reply_message", False)),
        )

    async def _get_file(self, file_id: Any) -> dict[str, str]:
        file_id = str(file_id)
        known = self.files.get(file_id)
        if known:
            if known.url:
                return {"file": "", "url": known.url, "file_name": known.name}
            file_id = known.file_id
        if file_id.startswith(("http://", "https://")):
            return {"file": "", "url": file_id, "file_name": Path(file_id).name}
        if adapter_name(self.native_bot) == "Telegram":
            info = await self.native_bot.get_file(file_id=file_id)
            file_path = str(getattr(info, "file_path", "") or "")
            config = getattr(self.native_bot, "bot_config", None)
            if file_path and config is not None:
                api_server = str(config.api_server).rstrip("/")
                return {
                    "file": "",
                    "url": f"{api_server}/file/bot{config.token}/{file_path}",
                    "file_name": (
                        self.files.get(file_id, ForeignFile(file_id, Path(file_path).name)).name
                    ),
                }
        return {"file": "", "url": "", "file_name": file_id}

    async def _group_members(self) -> list[dict[str, Any]]:
        if adapter_name(self.native_bot) == "Discord":
            guild_id = _as_int(getattr(self.native_event, "guild_id", 0))
            members = await self.native_bot.list_guild_members(
                guild_id=guild_id,
                limit=1000,
            )
            return [
                {
                    "user_id": int(item.user.id),
                    "nickname": item.user.username,
                    "card": getattr(item, "nick", None) or item.user.username,
                    "role": "member",
                }
                for item in members
                if getattr(item, "user", None) is not None
            ]
        admins = await self.native_bot.get_chat_administrators(
            chat_id=_group_id(self.native_event)
        )
        return [
            {
                "user_id": int(item.user.id),
                "nickname": item.user.first_name,
                "card": getattr(item, "custom_title", None) or item.user.first_name,
                "role": "owner" if item.status == "creator" else "admin",
            }
            for item in admins
        ]

    async def _group_member(self, user_id: Any) -> dict[str, Any]:
        if adapter_name(self.native_bot) == "Discord":
            member = await self.native_bot.get_guild_member(
                guild_id=_as_int(getattr(self.native_event, "guild_id", 0)),
                user_id=_as_int(user_id),
            )
            user = member.user
            return {
                "user_id": int(user.id),
                "nickname": user.username,
                "card": getattr(member, "nick", None) or user.username,
                "role": "member",
            }
        member = await self.native_bot.get_chat_member(
            chat_id=_group_id(self.native_event),
            user_id=_as_int(user_id),
        )
        return {
            "user_id": int(member.user.id),
            "nickname": member.user.first_name,
            "card": getattr(member, "custom_title", None) or member.user.first_name,
            "role": (
                "owner"
                if member.status == "creator"
                else "admin"
                if member.status == "administrator"
                else "member"
            ),
        }

    async def _set_group_ban(self, user_id: Any, duration: int) -> Any:
        if adapter_name(self.native_bot) == "Discord":
            until = (
                datetime.now(timezone.utc) + timedelta(seconds=duration)
                if duration > 0
                else None
            )
            return await self.native_bot.modify_guild_member(
                guild_id=_as_int(getattr(self.native_event, "guild_id", 0)),
                user_id=_as_int(user_id),
                communication_disabled_until=until,
            )
        from nonebot.adapters.telegram.model import ChatPermissions

        enabled = duration <= 0
        permissions = ChatPermissions(
            can_send_messages=enabled,
            can_send_audios=enabled,
            can_send_documents=enabled,
            can_send_photos=enabled,
            can_send_videos=enabled,
            can_send_video_notes=enabled,
            can_send_voice_notes=enabled,
            can_send_polls=enabled,
            can_send_other_messages=enabled,
        )
        return await self.native_bot.restrict_chat_member(
            chat_id=_group_id(self.native_event),
            user_id=_as_int(user_id),
            permissions=permissions,
            until_date=int(time.time()) + duration if duration > 0 else None,
        )

    async def _delete_message(self, message_id: Any) -> Any:
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.delete_message(
                channel_id=_group_id(self.native_event),
                message_id=_as_int(message_id),
            )
        return await self.native_bot.delete_message(
            chat_id=_group_id(self.native_event),
            message_id=_as_int(message_id),
        )

    async def _react(self, emoji: str) -> Any:
        if adapter_name(self.native_bot) == "Discord":
            return await self.native_bot.create_reaction(
                channel_id=_group_id(self.native_event),
                message_id=_message_id(self.native_event),
                emoji=emoji,
            )
        from nonebot.adapters.telegram.model import ReactionTypeEmoji

        return await self.native_bot.set_message_reaction(
            chat_id=_group_id(self.native_event),
            message_id=_message_id(self.native_event),
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )

    async def call_api(self, api: str, **data: Any) -> Any:
        if api in {"send_msg", "send_group_msg", "send_private_msg"}:
            private = api == "send_private_msg" or (
                api == "send_msg" and data.get("message_type") == "private"
            )
            target_id = (
                data.get("user_id")
                if private
                else data.get("group_id", self._current_target(False))
            )
            return await self._send(
                data.get("message", ""),
                target=self._target(target_id, private),
            )

        if api in {"upload_group_file", "upload_private_file"}:
            private = api == "upload_private_file"
            target_id = data.get("user_id") if private else data.get("group_id")
            path = Path(str(data["file"]))
            return await UniMessage.file(
                path=path,
                name=str(data.get("name") or path.name),
            ).send(
                target=self._target(target_id, private),
                bot=self.native_bot,
            )

        if api == "get_file":
            return await self._get_file(data.get("file_id", ""))
        if api == "get_group_member_list":
            return await self._group_members()
        if api == "get_group_member_info":
            return await self._group_member(data.get("user_id"))
        if api == "get_msg" and _as_int(data.get("message_id")) == _message_id(
            self.native_event
        ):
            message, _ = native_message_to_onebot(
                self.native_event,
                self.native_event.get_message(),
            )
            return {
                "message_id": _message_id(self.native_event),
                "user_id": _user_id(self.native_event),
                "message": message,
                "raw_message": message.extract_plain_text(),
            }
        if api == "delete_msg":
            return await self._delete_message(data.get("message_id"))
        if api == "set_group_ban":
            return await self._set_group_ban(
                data.get("user_id"),
                _as_int(data.get("duration"), 60),
            )
        if api == "set_group_kick":
            user_id = _as_int(data.get("user_id"))
            if adapter_name(self.native_bot) == "Discord":
                return await self.native_bot.remove_guild_member(
                    guild_id=_as_int(getattr(self.native_event, "guild_id", 0)),
                    user_id=user_id,
                )
            result = await self.native_bot.ban_chat_member(
                chat_id=_group_id(self.native_event),
                user_id=user_id,
            )
            if not data.get("reject_add_request", False):
                await self.native_bot.unban_chat_member(
                    chat_id=_group_id(self.native_event),
                    user_id=user_id,
                )
            return result
        if api in {"send_poke", "send_like"}:
            return await self._react("👋" if api == "send_poke" else "👍")
        if api in {"send_group_forward_msg", "send_private_forward_msg"}:
            private = api == "send_private_forward_msg"
            target_id = data.get("user_id") if private else data.get("group_id")
            nodes = data.get("messages") or data.get("message") or []
            result = []
            for node in nodes:
                node_data = getattr(node, "data", node)
                content = (
                    node_data.get("content")
                    if isinstance(node_data, dict)
                    else node_data
                )
                result.append(
                    await self._send(
                        content or "",
                        target=self._target(target_id, private),
                    )
                )
            return result
        if api in {
            "set_group_admin",
            "set_group_anonymous",
            "set_group_anonymous_ban",
            "set_group_card",
            "set_group_name",
            "set_group_portrait",
            "set_group_special_title",
            "set_group_whole_ban",
            "set_group_add_request",
            "set_essence_msg",
            "delete_essence_msg",
        }:
            return {"status": "unsupported", "api": api}
        return await self.native_bot.call_api(api, **data)


async def dispatch_as_onebot(bot: Bot, event: Event) -> None:
    compat_event, files = build_onebot_event(bot, event)
    compat_bot = OneBotCompatBot(bot, event, files)
    await handle_event(compat_bot, compat_event)


@event_preprocessor
async def bridge_foreign_message(bot: Bot, event: Event) -> None:
    if isinstance(event, OneBotMessageEvent):
        return
    if adapter_name(bot) not in SUPPORTED_ADAPTERS or event.get_type() != "message":
        return
    if _is_bot_message(event):
        raise IgnoredException("忽略其他机器人的消息")

    try:
        await dispatch_as_onebot(bot, event)
    except Exception:
        logger.exception(
            "跨平台 OneBot 兼容桥处理失败: adapter={}, event={}",
            adapter_name(bot),
            event.get_event_name(),
        )
    raise IgnoredException("消息已通过 OneBot V11 兼容桥分发")
