"""自动清理 OneBot 群文件中的过期非永久文件。

每次 NoneBot 启动时立即扫描一次，之后每 24 小时扫描一次。
插件不会预判群权限，而是直接尝试删除；没有权限的群会记录日志并跳过。
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import time
from collections.abc import Mapping
from typing import Any

from nonebot import get_bots, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot


RETENTION_DAYS = 3
SCAN_INTERVAL_SECONDS = 24 * 60 * 60
MIN_VALID_UPLOAD_TIMESTAMP = 946684800  # 2000-01-01，过滤 NapCat 返回的 0/无效时间
MAX_FUTURE_UPLOAD_SKEW_SECONDS = 24 * 60 * 60
TARGET_GROUP_IDS = {451586654, 722284223}

_cleanup_task: asyncio.Task[None] | None = None


def _timestamp(value: Any) -> float | None:
    """把 OneBot 常见的时间格式统一为 Unix 秒时间戳。"""
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return number

    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        try:
            normalized = text.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()

    if number > 10_000_000_000:
        number /= 1000
    return number


def _file_id(file_info: Mapping[str, Any]) -> str | None:
    value = file_info.get("file_id") or file_info.get("id")
    return str(value) if value is not None and str(value) else None


def _is_expired_non_permanent(file_info: Mapping[str, Any], cutoff: float) -> bool:
    """只匹配七天前上传、且明确设置了过期时间的文件。"""
    upload_time = _timestamp(file_info.get("upload_time"))
    dead_time = _timestamp(file_info.get("dead_time"))

    # NapCat 可能对刚上传或无法解析的文件返回 upload_time=0，必须跳过。
    # dead_time 缺失或 <= 0 按永久/未知处理，避免误删永久文件。
    return (
        upload_time is not None
        and upload_time >= MIN_VALID_UPLOAD_TIMESTAMP
        and upload_time <= time.time() + MAX_FUTURE_UPLOAD_SKEW_SECONDS
        and upload_time < cutoff
        and dead_time is not None
        and dead_time > 0
    )


def _collection(payload: Any, key: str) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    values = payload.get(key, [])
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, Mapping)]


async def _iter_group_files(bot: Bot, group_id: int):
    """遍历根目录和可访问的子文件夹。"""
    root = await bot.call_api("get_group_root_files", group_id=group_id)
    folders = _collection(root, "folders")
    for file_info in _collection(root, "files"):
        yield file_info

    visited: set[str] = set()
    pending = list(folders)
    while pending:
        folder = pending.pop(0)
        folder_id = folder.get("folder_id") or folder.get("id")
        if folder_id is None:
            continue
        folder_key = str(folder_id)
        if folder_key in visited:
            continue
        visited.add(folder_key)

        try:
            result = await bot.call_api(
                "get_group_files_by_folder",
                group_id=group_id,
                folder_id=folder_id,
            )
        except Exception as exc:
            logger.warning(
                f"[group_file_cleaner] 群 {group_id} 文件夹 {folder_key} 获取失败: {exc}"
            )
            continue

        for file_info in _collection(result, "files"):
            yield file_info
        pending.extend(_collection(result, "folders"))


async def _clean_bot(bot: Bot) -> tuple[int, int]:
    """清理一个 OneBot 实例，返回 (成功删除数, 失败数)。"""
    deleted = 0
    failed = 0
    cutoff = time.time() - RETENTION_DAYS * 24 * 60 * 60

    try:
        groups = await bot.call_api("get_group_list")
    except Exception as exc:
        logger.warning(f"[group_file_cleaner] Bot {bot.self_id} 获取群列表失败: {exc}")
        return deleted, failed

    if not isinstance(groups, list):
        logger.warning(f"[group_file_cleaner] Bot {bot.self_id} 群列表格式异常")
        return deleted, failed

    for group in groups:
        if not isinstance(group, Mapping) or group.get("group_id") is None:
            continue
        group_id = int(group["group_id"])
        if group_id not in TARGET_GROUP_IDS:
            continue

        try:
            async for file_info in _iter_group_files(bot, group_id):
                if not _is_expired_non_permanent(file_info, cutoff):
                    continue

                file_id = _file_id(file_info)
                if not file_id:
                    logger.warning(
                        f"[group_file_cleaner] 群 {group_id} 发现过期文件但缺少 file_id: {file_info}"
                    )
                    failed += 1
                    continue

                try:
                    await bot.call_api(
                        "delete_group_file",
                        group_id=group_id,
                        file_id=file_id,
                    )
                except Exception as exc:
                    # 没有群管权限、实现不支持删除或文件已被删，均不影响其他群。
                    failed += 1
                    logger.warning(
                        f"[group_file_cleaner] 群 {group_id} 删除 {file_id} 失败: {exc}"
                    )
                else:
                    deleted += 1
                    logger.info(
                        f"[group_file_cleaner] 群 {group_id} 已删除过期文件: "
                        f"{file_info.get('file_name') or file_info.get('name') or file_id}"
                    )
        except Exception as exc:
            failed += 1
            logger.warning(f"[group_file_cleaner] 群 {group_id} 扫描失败: {exc}")

    return deleted, failed


async def _run_cleanup() -> None:
    bots = [bot for bot in get_bots().values() if isinstance(bot, Bot)]
    if not bots:
        logger.info("[group_file_cleaner] 当前没有已连接的 OneBot V11 实例")
        return

    total_deleted = 0
    total_failed = 0
    for bot in bots:
        deleted, failed = await _clean_bot(bot)
        total_deleted += deleted
        total_failed += failed

    logger.info(
        f"[group_file_cleaner] 扫描完成：删除 {total_deleted} 个文件，"
        f"失败 {total_failed} 个"
    )


async def _cleanup_loop() -> None:
    # OneBot 连接通常在 NoneBot 启动回调之后建立，留出时间避免首轮扫描为空。
    await asyncio.sleep(30)
    while True:
        try:
            await _run_cleanup()
        except Exception as exc:
            logger.exception(f"[group_file_cleaner] 定时清理异常: {exc}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


driver = get_driver()


@driver.on_startup
async def _startup() -> None:
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info(
        f"[group_file_cleaner] 已启动：每 {SCAN_INTERVAL_SECONDS // 3600} 小时清理"
        f" {RETENTION_DAYS} 天前的非永久群文件"
    )


@driver.on_shutdown
async def _shutdown() -> None:
    global _cleanup_task
    if _cleanup_task is None:
        return
    _cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _cleanup_task
    _cleanup_task = None
