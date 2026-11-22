"""
/level - 回复一个 .mc 文件，调用外部预测脚本获取难度值
不回复或回复的不是 .mc 文件时静默不响应。
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import sys
import tempfile
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg


from src.plugin_runtime import tool_path
PREDICT_SCRIPT = tool_path("predict.exe")
POSTPROCESS_ENABLED = True


def postprocess_level(level: float) -> float:
    """对预测等级做连续分段后处理，40 以上使用指数外推。"""
    points = [
        (0.0, 2.0),
        (5.0, 3.0),
        (10.0, 8.0),
        (20.0, 20.0),
        (30.0, 31.0),
        (40.0, 41.0),
    ]

    if level <= points[0][0]:
        x0, y0 = points[0]
        x1, y1 = points[1]
        return y0 + (level - x0) * (y1 - y0) / (x1 - x0)

    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        if level <= x1:
            return y0 + (level - x0) * (y1 - y0) / (x1 - x0)

    anchor_x, anchor_y = points[-1]
    target_x = 60.0
    target_y = 120.0

    def solve_growth() -> float:
        """求解指数尾段的增长率，使 40 处斜率与前段一致且 60 映射到 120。"""
        left = 1e-6
        right = 1.0

        def equation(growth: float) -> float:
            return (math.exp((target_x - anchor_x) * growth) - 1.0) / growth - (target_y - anchor_y)

        while equation(right) < 0:
            right *= 2.0

        for _ in range(80):
            mid = (left + right) / 2.0
            if equation(mid) > 0:
                right = mid
            else:
                left = mid
        return (left + right) / 2.0

    growth = solve_growth()
    anchor_slope = points[-1][1] - points[-2][1]
    tail_scale = anchor_slope / growth
    tail_offset = anchor_y - tail_scale
    return tail_offset + tail_scale * math.exp((level - anchor_x) * growth)


def get_file_info_from_reply(event: MessageEvent) -> Optional[dict]:
    """从回复消息中提取文件信息。"""
    if not event.reply:
        return None
    for seg in event.reply.message:
        if seg.type == "file":
            data = seg.data
            return {
                "name": data.get("name") or data.get("filename") or data.get("file", "unknown"),
                "file_id": data.get("file_id"),
                "url": data.get("url", ""),
            }
    return None


async def download_file(bot: Bot, file_info: dict, dest: Path) -> bool:
    """下载文件到目标路径。"""
    file_url = file_info.get("url", "")
    file_id = file_info.get("file_id", "")

    try:
        if file_url and file_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                return True

        if file_id:
            try:
                file_data = await bot.call_api("get_file", file_id=file_id)
                url = file_data.get("url", "")
                local_path = file_data.get("file", "")

                if url and url.startswith(("http://", "https://")):
                    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        return True

                if local_path and Path(local_path).is_file():
                    shutil.copy(local_path, dest)
                    return True
            except Exception as e:
                logger.warning(f"[LevelPredict] get_file API 失败: {e}")

        if file_url and Path(file_url).is_file():
            shutil.copy(file_url, dest)
            return True

    except Exception as e:
        logger.error(f"[LevelPredict] 下载文件失败: {e}")

    return False


def extract_mcz_archive(mcz_path: Path, extract_dir: Path) -> bool:
    """将 .mcz 中的 .mc 文件解包到目录。"""
    try:
        with zipfile.ZipFile(mcz_path, "r") as archive:
            mc_found = False
            base_dir = extract_dir.resolve()

            for member in archive.infolist():
                if member.is_dir():
                    continue
                if Path(member.filename).suffix.lower() != ".mc":
                    continue

                target_path = (extract_dir / member.filename).resolve()
                if not target_path.is_relative_to(base_dir):
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                mc_found = True

            return mc_found
    except zipfile.BadZipFile:
        logger.error(f"[LevelPredict] 无效的 .mcz 文件: {mcz_path}")
        return False


async def run_predict_script(target_path: Path) -> Optional[list[dict]]:
    """调用外部 predict.py 并解析难度结果列表。"""
    if not PREDICT_SCRIPT.exists():
        logger.error(f"[LevelPredict] 预测脚本不存在: {PREDICT_SCRIPT}")
        return None

    process = await asyncio.create_subprocess_exec(
        str(PREDICT_SCRIPT),
        str(target_path),
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error(
            f"[LevelPredict] 预测脚本执行失败，returncode={process.returncode}, stderr={stderr_text}"
        )
        return None

    json_start = None
    lines = stdout_text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped.startswith("[") and not stripped.startswith("[OK]") and not stripped.startswith("[FATAL]"):
            json_start = index
            break

    if json_start is None:
        logger.error(f"[LevelPredict] 未找到 JSON 输出: {stdout_text}")
        if stderr_text:
            logger.error(f"[LevelPredict] stderr: {stderr_text}")
        return None

    try:
        json_blob = "\n".join(lines[json_start:]).lstrip()
        payload, _ = json.JSONDecoder().raw_decode(json_blob)
    except Exception as e:
        logger.error(f"[LevelPredict] 解析 JSON 失败: {e}; stdout={stdout_text}")
        if stderr_text:
            logger.error(f"[LevelPredict] stderr: {stderr_text}")
        return None

    if not isinstance(payload, list):
        return None

    if not payload:
        return []

    normalized: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if "level" not in item:
            continue
        normalized.append(item)

    if not normalized:
        return None

    return normalized


def format_level(level: float) -> str:
    """按四舍五入保留两位小数。"""
    value = Decimal(str(level)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


level_cmd = on_command("level", aliases={"lv"}, block=True, priority=5)


@level_cmd.handle()
async def handle_level(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    """Reserved command; intentionally silent until a replacement is connected."""
    return
