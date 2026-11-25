"""将命令或引用消息中的 QQ 表情贴到对应消息上。"""

from nonebot import logger, on_command
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="贴表情回应",
    description="将命令或引用消息中的 QQ 表情回应到对应消息上。",
    usage="/贴表情 <一个或多个 QQ 表情>，也可引用含 QQ 表情的消息后发送。",
)

sticker_reaction = on_command("贴表情", priority=5, block=True)


def _segments(message):
    if isinstance(message, str):
        return Message(message)
    if isinstance(message, dict):
        return (message,)
    return message or ()


def _segment_fields(segment):
    if isinstance(segment, dict):
        return segment.get("type"), segment.get("data") or {}
    return getattr(segment, "type", None), getattr(segment, "data", {})


def extract_reaction_ids(message) -> list[str]:
    """按顺序提取 QQ 内置表情和商城表情的回应 ID。"""
    reaction_ids = []
    for segment in _segments(message):
        segment_type, data = _segment_fields(segment)
        if segment_type == "face":
            reaction_id = str(data.get("id", "")).strip()
            if reaction_id.isascii() and reaction_id.isdigit():
                reaction_ids.append(reaction_id)
        elif segment_type == "mface" or (
            segment_type == "image" and data.get("emoji_id")
        ):
            reaction_id = str(data.get("emoji_id", "")).strip()
            if reaction_id:
                reaction_ids.append(reaction_id)
    return reaction_ids


def extract_reply_id(message) -> str | None:
    for segment in _segments(message):
        segment_type, data = _segment_fields(segment)
        if segment_type == "reply" and data.get("id"):
            return str(data["id"])
    return None


@sticker_reaction.handle()
async def handle_sticker_reaction(bot: Bot, event: MessageEvent, matcher: Matcher):
    current_message = event.get_message()
    reply_id = extract_reply_id(current_message)
    target_message_id = event.message_id
    source_message = current_message

    if reply_id:
        try:
            quoted_message = await bot.call_api("get_msg", message_id=reply_id)
        except Exception as error:
            logger.warning(
                "sticker_reaction: failed to read replied message {} ({})",
                reply_id,
                type(error).__name__,
            )
            await matcher.finish("无法读取引用的消息，请稍后重试。")
        if not isinstance(quoted_message, dict):
            await matcher.finish("无法读取引用的消息，请稍后重试。")
        target_message_id = reply_id
        source_message = quoted_message.get("message", ())

    reaction_ids = extract_reaction_ids(source_message)
    if not reaction_ids:
        if reply_id:
            await matcher.finish("引用的消息中没有可回应的 QQ 表情。")
        await matcher.finish("请在命令后附上一个或多个 QQ 表情。")

    succeeded = 0
    for reaction_id in reaction_ids:
        try:
            result = await bot.call_api(
                "set_msg_emoji_like",
                message_id=target_message_id,
                emoji_id=reaction_id,
                set=True,
            )
            if result is False:
                raise RuntimeError("reaction was rejected")
            succeeded += 1
        except Exception as error:
            logger.warning(
                "sticker_reaction: failed to react with emoji {} ({})",
                reaction_id,
                type(error).__name__,
            )

    if succeeded == 0:
        await matcher.finish("QQ 表情回应失败，请确认该表情可用后重试。")
