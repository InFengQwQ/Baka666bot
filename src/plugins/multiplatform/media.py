from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage


@dataclass
class IncomingMedia:
    name: str
    kind: str
    file_id: str | None = None
    url: str | None = None
    path: Path | None = None
    raw: bytes | None = None
    mimetype: str | None = None

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.lower()


def _kind_from_name(name: str, mimetype: str | None = None) -> str:
    guessed = mimetype or mimetypes.guess_type(name)[0] or ""
    if guessed.startswith("image/"):
        return "image"
    if guessed.startswith("video/"):
        return "video"
    if guessed.startswith("audio/"):
        return "audio"
    return "file"


def _discord_attachments(value: Any) -> Iterable[IncomingMedia]:
    for item in getattr(value, "attachments", []) or []:
        name = str(getattr(item, "filename", "file.bin"))
        mimetype = getattr(item, "content_type", None)
        yield IncomingMedia(
            name=name,
            kind=_kind_from_name(name, mimetype),
            url=str(getattr(item, "url", "") or ""),
            mimetype=mimetype,
        )


def _telegram_raw_message(event: Event) -> Any:
    update = getattr(event, "telegram_model", None)
    return getattr(update, "message", None) if update else None


def _telegram_media(event: Event, message: Any, raw: Any) -> Iterable[IncomingMedia]:
    seen: set[str] = set()
    if raw is None:
        raw = message
    if raw is None:
        return

    document = getattr(raw, "document", None)
    if document is not None:
        seen.add(str(document.file_id))
        name = str(getattr(document, "file_name", None) or "file.bin")
        yield IncomingMedia(
            name=name,
            kind="file",
            file_id=str(document.file_id),
            mimetype=getattr(document, "mime_type", None),
        )
    audio = getattr(raw, "audio", None)
    if audio is not None:
        seen.add(str(audio.file_id))
        name = str(getattr(audio, "file_name", None) or "audio.mp3")
        yield IncomingMedia(
            name=name,
            kind="audio",
            file_id=str(audio.file_id),
            mimetype=getattr(audio, "mime_type", None),
        )
    video = getattr(raw, "video", None)
    if video is not None:
        seen.add(str(video.file_id))
        name = str(getattr(video, "file_name", None) or "video.mp4")
        yield IncomingMedia(
            name=name,
            kind="video",
            file_id=str(video.file_id),
            mimetype=getattr(video, "mime_type", None),
        )
    animation = getattr(raw, "animation", None)
    if animation is not None:
        seen.add(str(animation.file_id))
        name = str(getattr(animation, "file_name", None) or "animation.mp4")
        yield IncomingMedia(
            name=name,
            kind="video",
            file_id=str(animation.file_id),
            mimetype=getattr(animation, "mime_type", None),
        )
    voice = getattr(raw, "voice", None)
    if voice is not None:
        seen.add(str(voice.file_id))
        yield IncomingMedia(
            name="voice.ogg",
            kind="audio",
            file_id=str(voice.file_id),
            mimetype=getattr(voice, "mime_type", None),
        )
    photo = getattr(raw, "photo", None)
    if photo:
        largest = photo[-1]
        seen.add(str(largest.file_id))
        yield IncomingMedia(
            name="image.jpg",
            kind="image",
            file_id=str(largest.file_id),
            mimetype="image/jpeg",
        )
    sticker = getattr(raw, "sticker", None)
    if sticker is not None:
        seen.add(str(sticker.file_id))
        yield IncomingMedia(
            name="sticker.webp",
            kind="image",
            file_id=str(sticker.file_id),
            mimetype="image/webp",
        )

    if message is not None:
        defaults = {
            "photo": ("image.jpg", "image"),
            "document": ("file.bin", "file"),
            "video": ("video.mp4", "video"),
            "animation": ("animation.mp4", "video"),
            "audio": ("audio.mp3", "audio"),
            "voice": ("voice.ogg", "audio"),
            "sticker": ("sticker.webp", "image"),
            "video_note": ("video.mp4", "video"),
        }
        for segment in message:
            if segment.type not in defaults:
                continue
            file_id = str(segment.data.get("file") or "")
            if not file_id or file_id in seen:
                continue
            default_name, kind = defaults[segment.type]
            yield IncomingMedia(
                name=str(
                    segment.data.get("file_name")
                    or segment.data.get("name")
                    or default_name
                ),
                kind=kind,
                file_id=file_id,
            )


def _native_media(event: Event) -> list[IncomingMedia]:
    result = list(_discord_attachments(event))
    if result:
        return result

    raw = _telegram_raw_message(event)
    return list(_telegram_media(event, getattr(event, "message", None), raw))


def _reply_media(event: Event) -> list[IncomingMedia]:
    reply = getattr(event, "reply_to_message", None) or getattr(
        event, "referenced_message", None
    )
    if reply is None:
        return []
    result = list(_discord_attachments(reply))
    if result:
        return result
    raw = getattr(reply, "telegram_model", None)
    return list(_telegram_media(event, getattr(reply, "message", None), raw))


def incoming_media(event: Event, *, include_reply: bool = True) -> list[IncomingMedia]:
    result = _native_media(event)
    if include_reply:
        result.extend(_reply_media(event))
    return result


def select_media(
    event: Event,
    *,
    suffixes: tuple[str, ...] = (),
    kinds: tuple[str, ...] = (),
    include_reply: bool = True,
) -> IncomingMedia | None:
    for item in incoming_media(event, include_reply=include_reply):
        if suffixes and item.suffix not in suffixes:
            continue
        if kinds and item.kind not in kinds:
            continue
        return item
    return None


async def download_media(bot: Bot, media: IncomingMedia, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if media.raw is not None:
        destination.write_bytes(media.raw)
        return True
    if media.path and media.path.is_file():
        shutil.copyfile(media.path, destination)
        return True
    if media.url:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(media.url)
            response.raise_for_status()
            destination.write_bytes(response.content)
        return True
    if media.file_id and bot.adapter.get_name() == "Telegram":
        file_info = await bot.get_file(file_id=media.file_id)
        file_path = getattr(file_info, "file_path", None)
        token = getattr(getattr(bot, "bot_config", None), "token", None)
        api_server = getattr(
            getattr(bot, "bot_config", None),
            "api_server",
            "https://api.telegram.org/",
        ).rstrip("/")
        if file_path and token:
            url = f"{api_server}/file/bot{token}/{file_path}"
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                destination.write_bytes(response.content)
            return True
    return False


async def send_path(bot: Bot, event: Event, path: Path, *, kind: str = "file"):
    if kind == "image":
        message = UniMessage.image(path=path, name=path.name)
    elif kind == "video":
        message = UniMessage.video(path=path, name=path.name)
    elif kind == "audio":
        message = UniMessage.audio(path=path, name=path.name)
    else:
        message = UniMessage.file(path=path, name=path.name)
    return await message.send(target=event, bot=bot)
