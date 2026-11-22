"""Suppress low-value bot notices before they reach QQ group chats.

The project has several independently loaded plugins, including locally
synced third-party plugins. Filtering at the OneBot API boundary keeps their
operational chatter out of groups without requiring every plugin to be edited.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.exception import MockApiException
from nonebot.log import logger


_QQ_MESSAGE_APIS = {
    "send_group_msg",
    "send_private_msg",
    "send_group_forward_msg",
    "send_private_forward_msg",
}
_MESSAGE_APIS = {
    "send_msg",
    "send_group_msg",
    "send_private_msg",
    "send_group_forward_msg",
    "send_private_forward_msg",
}

# These are intentionally semantic categories rather than a list of complete
# messages. New plugins can use different wording and still be quiet.
_PROGRESS_RE = re.compile(
    r"(?:"
    r"正在|即将|开始(?:处理|分析|生成|渲染|下载|转换|上传|发送)|"
    r"处理中|分析中|生成中|渲染中|下载中|转换中|上传中|发送中|"
    r"请稍候|请稍后|稍等|等待"
    r")",
    re.IGNORECASE,
)
_ACK_RE = re.compile(
    r"(?:"
    r"^(?:已收到|已接收|收到|接收到|检测到|已检测到).{0,120}"
    r"(?:文件|图包|谱面|链接|图片|视频|附件)|"
    r"(?:分析完成|处理完成).{0,80}(?:生成|发送|图片|文件)|"
    r"^(?:已完成|处理完成|任务完成|操作完成)[。.!！]*$"
    r")",
    re.IGNORECASE,
)
_ERROR_RE = re.compile(
    r"(?:"
    r"失败|错误|异常|出错|超时|不可用|无数据|无效|"
    r"未找到|找不到|无法|不能|请求频繁|余额不足|"
    r"未配置|key\s*无效|请反馈\s*bot\s*主人"
    r")",
    re.IGNORECASE,
)
_ACTIONABLE_RE = re.compile(
    r"(?:"
    r"格式|用法|示例|帮助|参数|"
    r"请(?:输入|提供|发送|回复|上传|选择)|"
    r"请输入|请选择|输入\s*[0-9０-９]+|"
    r"输入.{0,12}(?:取消|跳过)|"
    r"冷却中|仅限|只有主人|无权限|权限"
    r")",
    re.IGNORECASE,
)
_MEDIA_TYPES = {
    "image",
    "video",
    "record",
    "file",
    "audio",
    "music",
    "share",
    "json",
    "xml",
    "forward",
    "node",
}
_NON_CONTENT_TYPES = {"reply", "at"}


def _segment_type(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("type", "")).lower()
    return str(getattr(segment, "type", "")).lower()


def _segment_text(segment: Any) -> str:
    if isinstance(segment, dict):
        data = segment.get("data") or {}
        return str(data.get("text", ""))
    data = getattr(segment, "data", {}) or {}
    return str(data.get("text", ""))


def _text_is_actionable(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if not _ACTIONABLE_RE.search(stripped):
        return False

    # A failed request is normally just an operational notice. Keep only
    # interactive instructions that do not merely report a failure.
    if _ERROR_RE.search(stripped):
        return bool(
            re.search(
                r"输入\s*[0-9０-９]+|输入.{0,12}(?:取消|跳过)|"
                r"重新输入|请重新(?:发送|回复|输入)",
                stripped,
                re.IGNORECASE,
            )
        )
    return True


def is_non_constructive_text(text: str) -> bool:
    """Return whether text is progress, acknowledgement, or generic error noise."""

    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return True
    if _text_is_actionable(stripped):
        return False
    if _PROGRESS_RE.search(stripped):
        return True
    if _ACK_RE.search(stripped):
        return True
    if _ERROR_RE.search(stripped):
        return True
    return False


def _clean_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if _ERROR_RE.search(normalized) and not _text_is_actionable(normalized):
        return ""

    kept_lines: list[str] = []
    for line in text.splitlines():
        if line.strip() and not is_non_constructive_text(line):
            kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def _as_segments(message: Any) -> tuple[list[Any], str]:
    if isinstance(message, str):
        return [message], "string"
    if isinstance(message, MessageSegment):
        return [message], "segment"
    if isinstance(message, Message):
        return list(message), "message"
    if isinstance(message, list):
        return list(message), "list"
    if isinstance(message, dict):
        return [message], "dict"
    return [], "unknown"


def _rebuild_message(segments: list[Any], kind: str) -> Any:
    if kind == "string":
        return _segment_text(segments[0]) if segments else ""
    if kind == "segment":
        if len(segments) == 1:
            return segments[0]
        return Message(segments)
    if kind == "message":
        return Message(segments)
    if kind == "list":
        return segments
    if kind == "dict":
        return segments[0] if segments else {}
    return segments


def _node_content(node: Any) -> Any:
    if isinstance(node, dict):
        return (node.get("data") or {}).get("content")
    return (getattr(node, "data", {}) or {}).get("content")


def _node_with_content(node: Any, content: Any) -> Any:
    if isinstance(node, dict):
        copied = deepcopy(node)
        copied.setdefault("data", {})["content"] = content
        return copied
    copied = deepcopy(node)
    copied.data["content"] = content
    return copied


def _filter_forward_nodes(data: dict[str, Any]) -> tuple[bool, str]:
    key = "messages" if data.get("messages") is not None else "message"
    nodes = data.get(key)
    if not isinstance(nodes, list):
        return False, "unsupported_forward_shape"

    kept_nodes: list[Any] = []
    changed = False
    for node in nodes:
        content = _node_content(node)
        if content is None:
            kept_nodes.append(node)
            continue
        filtered, content_changed, reason = filter_message(content)
        if filtered is None:
            changed = True
            continue
        if content_changed:
            changed = True
            kept_nodes.append(_node_with_content(node, filtered))
        else:
            kept_nodes.append(node)

    if not kept_nodes:
        return True, "non_constructive_forward"
    if changed:
        data[key] = kept_nodes
    return changed, "filtered_forward_nodes" if changed else "allowed"


def filter_message(message: Any) -> tuple[Any, bool, str]:
    """Filter a OneBot message.

    Returns ``(message, changed, reason)``. ``message`` is empty when the
    entire outbound message is non-constructive and should be mocked.
    """

    segments, kind = _as_segments(message)
    if kind == "unknown":
        return message, False, "unsupported_message_type"
    if kind == "string":
        cleaned = _clean_text(message)
        if not cleaned:
            return None, True, "non_constructive_text"
        if cleaned != message:
            return cleaned, True, "removed_non_constructive_text"
        return message, False, "allowed"

    kept: list[Any] = []
    removed_text = False
    has_media = False

    for segment in segments:
        segment_type = _segment_type(segment)
        if segment_type == "text":
            text = _segment_text(segment)
            cleaned = _clean_text(text)
            if not cleaned:
                removed_text = bool(text.strip()) or removed_text
                continue
            if cleaned != text:
                removed_text = True
                if isinstance(segment, dict):
                    copied = deepcopy(segment)
                    copied.setdefault("data", {})["text"] = cleaned
                    kept.append(copied)
                else:
                    kept.append(MessageSegment.text(cleaned))
            else:
                kept.append(segment)
            continue

        if segment_type in _MEDIA_TYPES or (
            segment_type not in {"text"} | _NON_CONTENT_TYPES
        ):
            has_media = True
        kept.append(segment)

    has_meaningful_text = any(
        _segment_type(segment) == "text" and _segment_text(segment).strip()
        for segment in kept
    )
    has_content = has_meaningful_text or has_media
    if not has_content:
        return None, True, "non_constructive_text"
    if removed_text:
        return _rebuild_message(kept, kind), True, "removed_non_constructive_text"
    return message, False, "allowed"


def _is_qq_message_api(api: str, data: dict[str, Any]) -> bool:
    if api in _QQ_MESSAGE_APIS:
        return True
    if api != "send_msg":
        return False
    return (
        data.get("message_type") in {"group", "private"}
        or "group_id" in data
        or "user_id" in data
    )


def _is_real_onebot_bot(bot: Bot) -> bool:
    # OneBotCompatBot is a OneBot subclass used to relay Discord/Telegram
    # events. QQ filtering must not alter those native platform responses.
    if hasattr(bot, "native_bot"):
        return False
    return getattr(bot, "type", "") == "OneBot V11"


async def _filter_calling_api(
    bot: Bot,
    api: str,
    data: dict[str, Any],
) -> None:
    if (
        not _is_real_onebot_bot(bot)
        or api not in _MESSAGE_APIS
        or not _is_qq_message_api(api, data)
    ):
        return

    if api in {"send_group_forward_msg", "send_private_forward_msg"}:
        changed, reason = _filter_forward_nodes(data)
        if changed and reason == "non_constructive_forward":
            logger.info(
                "[outbound-filter] suppressed QQ forward notice: api={}, reason={}",
                api,
                reason,
            )
            raise MockApiException(
                {
                    "status": "filtered",
                    "reason": reason,
                    "message": "non-constructive QQ forward suppressed",
                }
            )
        if changed:
            logger.debug(
                "[outbound-filter] removed non-constructive QQ forward nodes: api={}",
                api,
            )
        return

    message = data.get("message")
    filtered, changed, reason = filter_message(message)
    if not changed:
        return

    if filtered is None:
        logger.info(
            "[outbound-filter] suppressed QQ notice: api={}, reason={}, text={!r}",
            api,
            reason,
            str(message)[:240],
        )
        raise MockApiException(
            {
                "status": "filtered",
                "reason": reason,
                "message": "non-constructive QQ notice suppressed",
            }
        )

    data["message"] = filtered
    logger.debug(
        "[outbound-filter] removed non-constructive text from QQ message: {!r}",
        str(message)[:240],
    )


_installed = False


def install_outbound_message_filter() -> None:
    global _installed
    if _installed:
        return
    Bot.on_calling_api(_filter_calling_api)
    _installed = True
