"""Personal avatar card: one reference image in, one composed card out."""

import asyncio
import re
from io import BytesIO

import httpx
from PIL import Image
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg

from .compose import CANVAS, NoSubject, render_card

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TEXT = 16
TOKEN_RE = re.compile(r'"([^"]*)"|(\S+)')
USAGE = '/个性头像 "InFeng" "4K ex1" [--size N]，带空格的部分用引号包住'

avatar_card = on_command("个性头像", aliases={"头像卡"}, priority=5, block=True)
_render_lock = asyncio.Semaphore(1)


def _parse(raw: str) -> tuple[str, str, int]:
    if raw.count('"') % 2:
        raise ValueError("引号没闭合")
    tokens = [quoted or bare for quoted, bare in TOKEN_RE.findall(raw)]

    size = CANVAS
    if "--size" in tokens:
        index = tokens.index("--size")
        value = tokens[index + 1] if index + 1 < len(tokens) else ""
        if not value.isdigit():
            raise ValueError(f"--size 需要一个 1~{CANVAS} 的整数")
        size = int(value)
        if not 1 <= size <= CANVAS:
            raise ValueError(f"--size 需在 1~{CANVAS} 之间")
        del tokens[index : index + 2]

    if len(tokens) > 2:
        raise ValueError(f"用法：{USAGE}")

    name = tokens[0].strip() if tokens else ""
    title = tokens[1].strip() if len(tokens) > 1 else ""
    if not name.isascii():
        raise ValueError("昵称只能用英文，卡片只排英文")
    if title and not title.isascii():
        raise ValueError("称号只能用英文，卡片只排英文")
    if len(name) > MAX_TEXT:
        raise ValueError(f"昵称最多 {MAX_TEXT} 个字符")
    if len(title) > MAX_TEXT:
        raise ValueError(f"称号最多 {MAX_TEXT} 个字符")
    return name, title, size


def _first_image(message: Message) -> MessageSegment | None:
    return next((segment for segment in message if segment.type == "image"), None)


def _replied_image(event: MessageEvent) -> MessageSegment | None:
    # the adapter already resolves the replied message into event.reply
    reply = event.reply
    return _first_image(reply.message) if reply else None


async def _download(segment: MessageSegment) -> bytes:
    url = str(segment.data.get("url") or "")
    if not url.startswith(("http://", "https://")):
        raise ValueError("图片缺少可下载地址")
    chunks: list[bytes] = []
    total = 0
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise ValueError("图片超过 20MB")
                chunks.append(chunk)
    return b"".join(chunks)


def _render(data: bytes, name: str, title: str, size: int) -> bytes:
    image = Image.open(BytesIO(data))
    image.load()
    return render_card(image, name, title, size)


@avatar_card.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    try:
        name, title, size = _parse(args.extract_plain_text())
    except ValueError as error:
        await avatar_card.finish(str(error))

    if not name:
        await avatar_card.finish(f"{USAGE}，图片放在同一条消息或回复里")

    segment = _first_image(event.get_message()) or _replied_image(event)
    if segment is None:
        await avatar_card.finish("没找到参考图：把图片和命令发在同一条消息里，或回复那张图")

    try:
        data = await _download(segment)
    except Exception as error:
        logger.warning(f"avatar_card: image download failed: {error}")
        await avatar_card.finish("参考图下载失败，换一张或稍后再试")

    async with _render_lock:
        try:
            card = await asyncio.to_thread(_render, data, name, title, size)
        except NoSubject:
            await avatar_card.finish("图里没有可识别的人物，换一张清楚点的")
        except Exception as error:
            logger.exception(f"avatar_card: render failed: {error}")
            await avatar_card.finish("生成失败，检查图片格式或稍后再试")

    await avatar_card.finish(MessageSegment.image(card))
