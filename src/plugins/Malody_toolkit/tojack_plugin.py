# -*- coding: utf-8 -*-
"""tojack 插件：把谱面 beat 分母统一到指定值 k（默认 4）。

指令:
    /tojack        → k=4
    /tojack 4      → k=4
    /tojack 8      → k=8

输入:
    - 回复一条 .mc/.mcz/.osu/.osz 文件消息，然后发送 /tojack [k]

输出:
    - 单文件: 原文件名.tojack{k}.mc
    - 压缩包: 原压缩包名.tojack{k}.mcz

提示策略:
    - 已知错误（无文件、格式不符、下载失败、转换失败等）只打印控制台，不向 QQ 发送提示。
    - 仅当出现未预期的异常时，向 QQ 发送固定文案“发送错误”。
"""

import asyncio
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from nonebot import on_regex
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException
from nonebot.log import logger

# ===== 配置 =====
from src.plugin_runtime import tool_path
TOJACK_SCRIPT = tool_path("tojack.py")
DEFAULT_K = 4
MAX_K = 10000

MAX_EXTRACT_SIZE = 100 * 1024 * 1024   # 解压后总大小上限 100MB
MAX_EXTRACT_FILES = 500                # 解压后文件数上限

CHART_FILE_EXTS = (".osu", ".mc")
CHART_ARCHIVE_EXTS = (".osz", ".mcz")
CHART_INPUT_EXTS = CHART_FILE_EXTS + CHART_ARCHIVE_EXTS

UNKNOWN_ERROR_TEXT = "发送错误"

# ===== 命令注册 =====
tojack = on_regex(
    r"^/?tojack(?:\s+\d+)?$",
    flags=re.IGNORECASE,
    block=True,
)


# ===== 通用工具 =====
def _file_info_from_message(message) -> dict | None:
    if not message:
        return None
    for segment in message:
        if segment.type != "file":
            continue
        data = segment.data
        name = (
            data.get("name")
            or data.get("filename")
            or data.get("file_name")
            or data.get("file")
            or "unknown"
        )
        return {
            "name": Path(str(name)).name or "unknown",
            "file_id": data.get("file_id") or data.get("id"),
            "url": data.get("url") or data.get("file") or "",
        }
    return None


def _event_file_info(event: MessageEvent) -> dict | None:
    current = _file_info_from_message(getattr(event, "message", None))
    if current:
        return current
    reply = getattr(event, "reply", None)
    return _file_info_from_message(reply.message if reply else None)


def _local_path_from_source(source: str) -> Path | None:
    source = str(source or "").strip()
    if source.startswith("file://"):
        parsed = unquote(urlparse(source).path)
        if len(parsed) >= 3 and parsed[0] == "/" and parsed[2] == ":":
            parsed = parsed[1:]
        path = Path(parsed)
    else:
        try:
            path = Path(source)
        except (OSError, ValueError):
            return None
    try:
        return path if path.is_file() else None
    except OSError:
        return None


async def _download_url(url: str, destination: Path) -> None:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        destination.write_bytes(response.content)


async def _download_file_info(bot: Bot, file_info: dict, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = str(file_info.get("url") or "").strip()

    local_path = _local_path_from_source(source)
    if local_path:
        shutil.copyfile(local_path, destination)
        return True
    if source.startswith(("http://", "https://")):
        await _download_url(source, destination)
        return True

    file_id = file_info.get("file_id")
    if not file_id:
        return False

    try:
        file_data = await bot.get_file(file_id=file_id)
    except Exception:
        file_data = await bot.call_api("get_file", file_id=file_id)
    file_url = str(file_data.get("url") or "").strip()
    cached_file = str(file_data.get("file") or "").strip()

    local_path = _local_path_from_source(cached_file)
    if local_path:
        shutil.copyfile(local_path, destination)
        return True
    if file_url.startswith(("http://", "https://")):
        await _download_url(file_url, destination)
        return True
    return False


def _archive_member_path(root: Path, member_name: str) -> Path:
    root_resolved = root.resolve()
    target = (root / member_name).resolve()
    if not target.is_relative_to(root_resolved):
        raise ValueError(f"压缩包包含非法路径：{member_name}")
    return target


def _extract_archive_safely(archive_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total_size = 0
    file_count = 0
    with zipfile.ZipFile(archive_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            file_count += 1
            total_size += member.file_size
            if total_size > MAX_EXTRACT_SIZE or file_count > MAX_EXTRACT_FILES:
                raise ValueError("压缩包超过安全限制")
            target = _archive_member_path(output_dir, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)


def _repack_archive(source_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
            archive.write(file_path, file_path.relative_to(source_dir).as_posix())


def _decode_process_output(value: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            decoded = value.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if decoded:
            return decoded
    return value.decode("utf-8", "replace").strip()


async def _run_python_tool(
    script_path: Path,
    input_path: Path,
    extra_args: tuple[str, ...] = (),
) -> Path:
    if not script_path.is_file():
        raise FileNotFoundError(f"找不到工具脚本：{script_path}")

    before = {path for path in input_path.parent.iterdir() if path.is_file()}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        str(input_path),
        *extra_args,
        cwd=str(input_path.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    generated = sorted(
        path
        for path in input_path.parent.iterdir()
        if path.is_file() and path not in before and path.suffix.lower() == ".mc"
    )
    if process.returncode != 0 or not generated:
        detail = _decode_process_output(stderr) or _decode_process_output(stdout)
        raise RuntimeError(detail or f"{script_path.name} 未生成输出文件")
    return generated[0]


async def _run_native_tool(
    executable_path: Path,
    input_path: Path,
    extra_args: tuple[str, ...] = (),
) -> Path:
    if not executable_path.is_file():
        raise FileNotFoundError(f"找不到工具程序：{executable_path}")
    command = (str(executable_path), str(input_path), *extra_args)
    logger.info(
        "[tojack] executing: "
        + " ".join(f'"{value}"' if " " in value else value for value in command)
    )
    before = {path for path in input_path.parent.iterdir() if path.is_file()}
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(input_path.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    logger.info(
        f"[tojack] exit={process.returncode} input={input_path.name} args={list(extra_args)}"
    )
    generated = sorted(
        path
        for path in input_path.parent.iterdir()
        if path.is_file() and path not in before and path.suffix.lower() == ".mc"
    )
    if process.returncode != 0 or not generated:
        detail = _decode_process_output(stderr) or _decode_process_output(stdout)
        if detail:
            raise RuntimeError(detail)
        if process.returncode != 0:
            raise RuntimeError(
                f"{executable_path.name} 退出码 {process.returncode}，未生成输出文件"
            )
        raise RuntimeError(f"{executable_path.name} 未生成输出文件")
    return generated[0]


async def _run_chart_tool_process(
    tool_path: Path,
    input_path: Path,
    extra_args: tuple[str, ...] = (),
) -> Path:
    if tool_path.suffix.lower() == ".exe":
        return await _run_native_tool(tool_path, input_path, extra_args)
    return await _run_python_tool(tool_path, input_path, extra_args)


def _import_osu_to_mc():
    """兼容相对导入 / 绝对导入 / plugins.<pkg> 导入。"""
    try:
        from .om2ma import osu_to_mc  # type: ignore
        return osu_to_mc
    except (ImportError, ValueError):
        pass
    try:
        from om2ma import osu_to_mc  # type: ignore
        return osu_to_mc
    except ImportError:
        pass
    try:
        from plugins.om2ma import osu_to_mc  # type: ignore
        return osu_to_mc
    except ImportError:
        pass
    raise ImportError("找不到 om2ma 模块，请确保 om2ma.py 与本插件同目录")


async def _convert_single_chart(
    input_path: Path,
    script_path: Path,
    script_args: tuple[str, ...] = (),
) -> Path:
    source = input_path
    if input_path.suffix.lower() == ".osu":
        osu_to_mc = _import_osu_to_mc()
        try:
            mc_text = osu_to_mc(input_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as exc:
            raise ValueError(f"解析 osu 文件失败: {exc}") from exc
        source = input_path.with_suffix(".mc")
        source.write_text(mc_text, encoding="utf-8")
    return await _run_chart_tool_process(script_path, source, script_args)


async def _convert_archive(
    input_path: Path,
    script_path: Path,
    output_suffix: str,
    script_args: tuple[str, ...] = (),
) -> Path:
    work_dir = input_path.parent / f"{input_path.stem}_work"
    _extract_archive_safely(input_path, work_dir)

    osu_files = sorted(
        path for path in work_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".osu"
    )
    if osu_files:
        osu_to_mc = _import_osu_to_mc()
        for osu_path in osu_files:
            try:
                mc_text = osu_to_mc(
                    osu_path.read_text(encoding="utf-8", errors="ignore")
                )
            except Exception as exc:
                raise ValueError(f"解析 osu 文件失败 {osu_path.name}: {exc}") from exc
            mc_path = osu_path.with_suffix(".mc")
            if mc_path.exists():
                index = 1
                while True:
                    candidate = osu_path.with_name(
                        f"{osu_path.stem}__from_osu_{index}.mc"
                    )
                    if not candidate.exists():
                        mc_path = candidate
                        break
                    index += 1
            mc_path.write_text(mc_text, encoding="utf-8")
            osu_path.unlink(missing_ok=True)

    mc_files = sorted(
        path for path in work_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".mc"
    )
    if not mc_files:
        raise ValueError("压缩包中没有找到 .mc 或 .osu 谱面文件")

    for mc_path in mc_files:
        await _run_chart_tool_process(script_path, mc_path, script_args)
        mc_path.unlink(missing_ok=True)

    output_path = input_path.parent / f"{input_path.stem}{output_suffix}.mcz"
    _repack_archive(work_dir, output_path)
    return output_path


async def _send_result_file(bot: Bot, event: MessageEvent, path: Path) -> None:
    if isinstance(event, GroupMessageEvent):
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(path.absolute()),
            name=path.name,
        )
    elif isinstance(event, PrivateMessageEvent):
        await bot.upload_private_file(
            user_id=event.user_id,
            file=str(path.absolute()),
            name=path.name,
        )
    else:
        raise ValueError(f"不支持的消息类型：{type(event).__name__}")


# ===== 业务入口 =====
async def _run_tojack(bot: Bot, event: MessageEvent, matcher, k: int) -> None:
    file_info = _event_file_info(event)
    if not file_info:
        logger.error("[tojack] 未找到可用的文件消息")
        await matcher.finish()

    file_name = file_info["name"]
    if Path(file_name).suffix.lower() not in CHART_INPUT_EXTS:
        logger.error(f"[tojack] 不支持的文件格式: {file_name}")
        await matcher.finish()

    script_args = (str(k),)
    output_suffix = f"_tojack{k}"

    try:
        with tempfile.TemporaryDirectory(prefix="tojack_") as temporary:
            root = Path(temporary)
            input_path = root / Path(file_name).name
            if not await _download_file_info(bot, file_info, input_path):
                logger.error(f"[tojack] 文件下载失败: {file_name}")
                await matcher.finish()

            suffix = input_path.suffix.lower()
            if suffix in CHART_FILE_EXTS:
                output = await _convert_single_chart(
                    input_path, TOJACK_SCRIPT, script_args
                )
            elif suffix in CHART_ARCHIVE_EXTS:
                output = await _convert_archive(
                    input_path, TOJACK_SCRIPT, output_suffix, script_args
                )
            else:
                logger.error(f"[tojack] 不支持的谱面格式: {suffix}")
                await matcher.finish()

            await _send_result_file(bot, event, output)
    except FinishedException:
        raise
    except (ValueError, FileNotFoundError, RuntimeError, zipfile.BadZipFile):
        # 已知异常：只打印控制台，不打扰用户
        logger.exception("[tojack] 处理失败")
        await matcher.finish()
    except Exception:
        # 未知异常：给用户一个固定提示
        logger.exception("[tojack] 未知错误")
        await matcher.finish(UNKNOWN_ERROR_TEXT)


@tojack.handle()
async def _(bot: Bot, event: MessageEvent):
    # 忽略 Bot 自身发出的消息
    event_user_id = getattr(event, "user_id", None)
    bot_self_id = getattr(bot, "self_id", None)
    if (
        event_user_id is not None
        and bot_self_id is not None
        and str(event_user_id) == str(bot_self_id)
    ):
        await tojack.finish()

    text = event.get_plaintext().strip()
    match = re.fullmatch(r"/?tojack(?:\s+(\d+))?", text, flags=re.IGNORECASE)
    if not match:
        await tojack.finish()

    k = int(match.group(1)) if match.group(1) else DEFAULT_K
    if k <= 0:
        logger.error(f"[tojack] 参数非法: k={k}")
        await tojack.finish()
    if k > MAX_K:
        logger.error(f"[tojack] 参数过大: k={k} > {MAX_K}")
        await tojack.finish()

    await _run_tojack(bot, event, tojack, k)
