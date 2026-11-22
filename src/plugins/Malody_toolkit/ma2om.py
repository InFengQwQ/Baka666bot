import asyncio
import re
import sys
from pathlib import Path
import tempfile
import httpx
import shutil
from urllib.parse import unquote, urlparse
from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import CommandArg

import zipfile

# 在文件头部添加这两个常量，便于修改
MAX_EXTRACT_SIZE = 100 * 1024 * 1024   # 最大解压后总大小 100MB
MAX_EXTRACT_FILES = 500                # 最多文件数量

# 注册所有的命令
ma2om = on_command("ma2om", block=True)
mp32ogg = on_command("mp32ogg", block=True)
ncm2mp3 = on_command("ncm2mp3", block=True)
ncm2ogg = on_command("ncm2ogg", block=True)
unzip_file = on_command("解压", aliases={"unzip"}, block=True)
toinverse = on_command("toinverse", block=True)
to_nk = on_regex(
    r"^/?to[1-9]\d*k(?:\s+\S+){0,3}$",
    flags=re.IGNORECASE,
    block=True,
)



# 集中配置不同指令对应的工具路径与支持的文件后缀
from src.plugin_runtime import tool_path
CONFIGS = {
    "ma2om": {
        "exe": str(tool_path("ma2om.exe")),
        "exts": (".mcz", ".zip")
    },
    "mp32ogg": {
        "exe": str(tool_path("mp32ogg.exe")),
        "exts": (".mp3",)
    },
    "ncm2mp3": {
        "exe": str(tool_path("ncm2mp3.exe")),
        "exts": (".ncm",)
    },
    "ncm2ogg": {
        "exe": str(tool_path("ncm2ogg.exe")),
        "exts": (".ncm",)
    },
    "unzip": {
        "exe": str(tool_path("DragUnzip.exe")),
        "exts": (".zip", ".osz", ".mcz")
    }
}

TOINVERSE_SCRIPT = tool_path("inverse.py")
PRONTOM_EXE = tool_path("prontom.exe")
CHART_FILE_EXTS = (".osu", ".mc")
CHART_ARCHIVE_EXTS = (".osz", ".mcz")
CHART_INPUT_EXTS = CHART_FILE_EXTS + CHART_ARCHIVE_EXTS


def _file_info_from_message(message) -> dict | None:
    """从 OneBot 消息中提取第一个文件，兼容不同实现的字段命名。"""
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
    """优先取当前消息中的文件，其次取回复消息中的文件。"""
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
    """下载 OneBot 文件，兼容 URL、缓存路径和 file_id。"""
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
    """解压谱面包并限制总大小、文件数，同时防止路径穿越。"""
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
        "[chart-tool] executing: "
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
        f"[chart-tool] exit={process.returncode} "
        f"input={input_path.name} args={list(extra_args)}"
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
    logger.info(
        f"[chart-tool] generated={[path.name for path in generated]} "
        f"stdout={_decode_process_output(stdout)}"
    )
    return generated[0]


async def _run_chart_tool_process(
    tool_path: Path,
    input_path: Path,
    extra_args: tuple[str, ...] = (),
) -> Path:
    if tool_path.suffix.lower() == ".exe":
        return await _run_native_tool(tool_path, input_path, extra_args)
    return await _run_python_tool(tool_path, input_path, extra_args)


def _parse_osu_reference(text: str) -> tuple[str, str] | None:
    """解析 osu! beatmap URL、直接 .osu/.osz URL 和常见 bid 写法。"""
    value = text.strip().strip("<>")
    if not value:
        return None

    if re.fullmatch(r"(?:bid\s*[:=]?\s*|b\s*)?\d+", value, re.IGNORECASE):
        beatmap_id = re.search(r"\d+", value).group()
        return f"https://osu.ppy.sh/osu/{beatmap_id}", f"beatmap_{beatmap_id}.osu"

    if re.match(r"(?:www\.)?osu\.ppy\.sh/", value, re.IGNORECASE):
        value = f"https://{value}"
    if not re.match(r"https?://", value, re.IGNORECASE):
        return None

    parsed = urlparse(value)
    path = unquote(parsed.path).rstrip("/")
    path_parts = [part for part in path.split("/") if part]
    host = parsed.netloc.lower().split(":", 1)[0]

    if host.endswith("osu.ppy.sh"):
        beatmap_id = None
        if len(path_parts) >= 2 and path_parts[0] in {"b", "beatmaps", "beatmap"}:
            if path_parts[1].isdigit():
                beatmap_id = path_parts[1]
        if beatmap_id:
            return (
                f"https://osu.ppy.sh/osu/{beatmap_id}",
                f"beatmap_{beatmap_id}.osu",
            )
        if path_parts and path_parts[0] == "beatmapsets" and len(path_parts) >= 2:
            fragment_parts = [part for part in parsed.fragment.split("/") if part]
            for part in reversed(fragment_parts):
                if part.isdigit():
                    beatmap_id = part
                    break
            if beatmap_id:
                return (
                    f"https://osu.ppy.sh/osu/{beatmap_id}",
                    f"beatmap_{beatmap_id}.osu",
                )
            if path_parts[1].isdigit():
                set_id = path_parts[1]
                return (
                    f"https://osu.ppy.sh/beatmapsets/{set_id}/download?noVideo=1",
                    f"beatmapset_{set_id}.osz",
                )

    suffix = Path(path).suffix.lower()
    if suffix in {".osu", ".osz"}:
        return value, Path(path).name
    return None


async def _download_osu_reference(reference: tuple[str, str], destination_dir: Path) -> Path:
    url, suggested_name = reference
    destination = destination_dir / Path(suggested_name).name
    await _download_url(url, destination)

    # osu! 的下载接口可能重定向到另一种资源，按文件头纠正后缀。
    data = destination.read_bytes()
    if data.startswith(b"PK\x03\x04") and destination.suffix.lower() != ".osz":
        corrected = destination.with_suffix(".osz")
        destination.replace(corrected)
        return corrected
    if not data.startswith(b"PK\x03\x04") and destination.suffix.lower() == ".osz":
        corrected = destination.with_suffix(".osu")
        destination.replace(corrected)
        return corrected
    return destination


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


async def _convert_single_chart(
    input_path: Path,
    script_path: Path,
    script_args: tuple[str, ...] = (),
) -> Path:
    """把单个 .mc 或 .osu 谱面转换为外部脚本需要的 .mc。"""
    source = input_path
    if input_path.suffix.lower() == ".osu":
        from .om2ma import osu_to_mc

        try:
            mc_text = osu_to_mc(input_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as exc:
            raise ValueError(f"解析 osu 文件失败：请反馈bot主人") from exc
        source = input_path.with_suffix(".mc")
        source.write_text(mc_text, encoding="utf-8")
    return await _run_chart_tool_process(script_path, source, script_args)


async def _convert_archive(
    input_path: Path,
    script_path: Path,
    output_suffix: str,
    script_args: tuple[str, ...] = (),
) -> Path:
    """处理 osz/mcz 中的所有谱面，并重新打包成 mcz。"""
    work_dir = input_path.parent / f"{input_path.stem}_work"
    _extract_archive_safely(input_path, work_dir)

    osu_files = sorted(
        path for path in work_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".osu"
    )
    if osu_files:
        from .om2ma import osu_to_mc

        for osu_path in osu_files:
            try:
                mc_text = osu_to_mc(
                    osu_path.read_text(encoding="utf-8", errors="ignore")
                )
            except Exception as exc:
                raise ValueError(f"解析 osu 文件失败：{osu_path.name}: 请反馈bot主人") from exc
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


async def _run_chart_tool(
    bot: Bot,
    event: MessageEvent,
    matcher,
    tool_name: str,
    args_text: str,
    script_path_override: Path | None = None,
    script_args_override: tuple[str, ...] | None = None,
    output_suffix_override: str | None = None,
) -> None:
    file_info = _event_file_info(event)
    raw_args = args_text.strip()
    script_args: tuple[str, ...] = ()

    if tool_name == "toinverse":
        values = raw_args.split() if raw_args else []
        if len(values) not in {0, 2}:
            await matcher.finish("用法：回复 .mc/.mcz 文件发送 /toinverse，或附加 n m 两个整数。")
        if values:
            if not all(re.fullmatch(r"-?\d+", value) for value in values):
                await matcher.finish("toinverse 参数必须是两个整数：/toinverse n m")
            if int(values[1]) == 0:
                await matcher.finish("toinverse 的 m 不能为 0。")
            script_args = (values[0], values[1])
        if not file_info:
            await matcher.finish("请发送或回复 .mc/.osu/.mcz/.osz 文件。")
        if Path(file_info["name"]).suffix.lower() not in CHART_INPUT_EXTS:
            await matcher.finish("toinverse 只支持 .mc、.osu、.mcz、.osz 文件。")
    else:
        reference = _parse_osu_reference(raw_args) if raw_args else None
        if not file_info and not reference:
            await matcher.finish(
                "请发送或回复 .osu/.osz/.mc/.mcz 文件，或提供 osu 链接 / bid。"
            )
        if script_args_override is not None:
            script_args = script_args_override
        if file_info and Path(file_info["name"]).suffix.lower() not in CHART_INPUT_EXTS:
            await matcher.finish(f"{tool_name} 只支持 .osu、.osz、.mc、.mcz 文件。")

    script_path = script_path_override or (
        TOINVERSE_SCRIPT if tool_name == "toinverse" else PRONTOM_EXE
    )
    output_suffix = output_suffix_override or (
        "_inverse" if tool_name == "toinverse" else "_to8K"
    )

    try:
        with tempfile.TemporaryDirectory(prefix=f"{tool_name}_") as temporary:
            root = Path(temporary)
            if file_info:
                input_path = root / Path(file_info["name"]).name
                if not await _download_file_info(bot, file_info, input_path):
                    await matcher.finish("文件下载失败，请重试。")
            else:
                input_path = await _download_osu_reference(reference, root)

            suffix = input_path.suffix.lower()
            if suffix == ".mc" or suffix == ".osu":
                output = await _convert_single_chart(input_path, script_path, script_args)
            elif suffix in CHART_ARCHIVE_EXTS:
                output = await _convert_archive(
                    input_path, script_path, f"{output_suffix}", script_args
                )
            else:
                await matcher.finish("不支持的谱面格式。")

            await _send_result_file(bot, event, output)
    except FinishedException:
        raise
    except (ValueError, FileNotFoundError, RuntimeError, zipfile.BadZipFile) as exc:
        logger.exception(f"[{tool_name}] 处理失败")
        await matcher.finish(f"{tool_name} 处理失败：请反馈bot主人")
    except Exception as exc:
        logger.exception(f"[{tool_name}] 出错")
        await matcher.finish(f"{tool_name} 出错，请检查后台日志。")

async def handle_conversion(matcher, bot: Bot, event: MessageEvent, tool_key: str):
    config = CONFIGS.get(tool_key)
    if not config:
        logger.error(f"找不到工具配置: {tool_key}")
        await matcher.finish()
        
    exe_path = config["exe"]
    valid_exts = config["exts"]

    # 1. 检查是否回复了消息
    if not event.reply:
        logger.error("没有回复文件")
        await matcher.finish()
    
    reply_msg = event.reply.message
    file_id = None
    file_name = f"unknown{valid_exts[0]}"
    file_url = None

    # 2. 从回复的消息中提取文件 segment (OneBot v11 文件格式)
    for seg in reply_msg:
        if seg.type == "file":
            # 适配 NapCat/OneBot v11 的多种命名习惯
            file_name = seg.data.get("name") or seg.data.get("filename") or seg.data.get("file") or file_name
            file_id = seg.data.get("file_id")
            file_url = seg.data.get("url")
            break
            
    if not file_id:
        logger.error("找不到文件ID")
        await matcher.finish()
        
    if not any(file_name.lower().endswith(ext) for ext in valid_exts):
        logger.error(f"文件格式不正确，期望: {valid_exts}")
        await matcher.finish()

    logger.info(f"[{tool_key}] 开始处理 {file_name}...")
    
    try:
        # 3. 如果事件里没有提供 url，调用 API 获取文件下载直链或本地路径
        if not file_url:
            file_info = await bot.get_file(file_id=file_id)
            file_url = file_info.get("url")
            # 在某些 OneBot 实现中（如 NapCat ），如果文件被缓存，可能会提供本地 file 路径而不是 URL
            local_file = file_info.get("file") 
            if not file_url and local_file:
                file_url = local_file

        if not file_url:
            logger.error("未获取到下载链接")
            await matcher.finish()

        # 4. 创建自动销毁的临时目录。Python的这个模块能保证它一定是个全新、只有此次任务专属的空文件夹
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / file_name
            
            # 下载或复制文件
            if Path(file_url).is_file():
                shutil.copy(file_url, input_path)
            elif file_url.startswith("http://") or file_url.startswith("https://"):
                async with httpx.AsyncClient() as client:
                    resp = await client.get(file_url, timeout=120.0, follow_redirects=True)
                    resp.raise_for_status()
                    input_path.write_bytes(resp.content)
            else:
                logger.error("无法识别连接格式")
                await matcher.finish()
            
            if not Path(exe_path).exists():
                logger.error(f"找不到转换工具: {exe_path}")
                await matcher.finish()

            # --- 关键步骤：记录目前文件夹里的文件集合（这时候里面只有这1个原始文件）---
            files_before = set(temp_dir_path.iterdir())

            # 5. 运行命令行指令
            proc = await asyncio.create_subprocess_exec(
                exe_path,
                str(input_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            # --- 关键步骤：再次扫描文件夹获取执行工具后的文件集合 ---
            files_after = set(temp_dir_path.iterdir())
            
            # 两个集合相减，得出所有新生成的文件
            new_files = files_after - files_before
            
            if not new_files:
                error_msg = stderr.decode('gbk', 'ignore') or stdout.decode('gbk', 'ignore')
                logger.error(f"[{tool_key}] 转换失败，未监控到任何新文件生成: {error_msg}")
                await matcher.finish()
            
            # 6. 把新生成的文件挨个全部发出去
            for new_file in new_files:
                logger.info(f"[{tool_key}] 成功生成了 {new_file.name}，正在发送...")
                if isinstance(event, GroupMessageEvent):
                    await bot.upload_group_file(
                        group_id=event.group_id,
                        file=str(new_file.absolute()),
                        name=new_file.name
                    )
                elif isinstance(event, PrivateMessageEvent):
                    await bot.upload_private_file(
                        user_id=event.user_id,
                        file=str(new_file.absolute()),
                        name=new_file.name
                    )
            
    except Exception as e:
        logger.error(f"[{tool_key}] 转换出错: {e}")
        await matcher.finish()
async def handle_unzip(matcher, bot: Bot, event: MessageEvent):
    # 不必再依赖 CONFIGS["unzip"] 的 exe 路径，只保留后缀用于提示（可选）
    valid_exts = (".zip", ".osz", ".mcz")

    # 1. 必须回复一条文件消息
    if not event.reply:
        logger.error("请回复一个压缩文件")
        await matcher.finish()

    reply_msg = event.reply.message
    file_id = None
    file_name = "archive.zip"
    file_url = None

    for seg in reply_msg:
        if seg.type == "file":
            file_name = seg.data.get("name") or seg.data.get("filename") or seg.data.get("file") or file_name
            file_id = seg.data.get("file_id")
            file_url = seg.data.get("url")
            break

    if not file_id:
        logger.error("回复消息中没有文件")
        await matcher.finish()

    logger.info(f"[unzip] 开始处理 {file_name}...")

    try:
        # 2. 获取文件下载链接 / 本地路径（保持原逻辑）
        if not file_url:
            file_info = await bot.get_file(file_id=file_id)
            file_url = file_info.get("url")
            local_file = file_info.get("file")
            if not file_url and local_file:
                file_url = local_file

        if not file_url:
            logger.error("未获取到下载链接")
            await matcher.finish()

        # 3. 创建临时目录，下载/复制压缩包（保持原逻辑）
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / file_name

            if Path(file_url).is_file():
                shutil.copy(file_url, input_path)
            elif file_url.startswith(("http://", "https://")):
                async with httpx.AsyncClient() as client:
                    resp = await client.get(file_url, timeout=120.0, follow_redirects=True)
                    resp.raise_for_status()
                    input_path.write_bytes(resp.content)
            else:
                logger.error("无法识别的文件链接格式")
                await matcher.finish()

            # ---------- 4. 用 zipfile 解压，并实时防御炸弹 ----------
            extracted_files = []
            total_size = 0
            file_count = 0

            # 由于 zipfile 解压是同步操作，用 run_in_executor 避免阻塞事件循环
            def extract_with_limit(zip_path, extract_dir):
                nonlocal total_size, file_count, extracted_files
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for member in zf.infolist():
                        # 跳过目录（只计文件）
                        if member.is_dir():
                            continue

                        # 提前检查：当前文件大小 + 已有大小是否超限
                        if total_size + member.file_size > MAX_EXTRACT_SIZE:
                            raise ValueError(f"解压后总大小将超过 {MAX_EXTRACT_SIZE} 字节，疑似压缩包炸弹")
                        if file_count + 1 > MAX_EXTRACT_FILES:
                            raise ValueError(f"解压后文件数将超过 {MAX_EXTRACT_FILES} 个，疑似压缩包炸弹")

                        # 解压单个文件
                        zf.extract(member, extract_dir)
                        total_size += member.file_size
                        file_count += 1
                        extracted_files.append(Path(extract_dir) / member.filename)

            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    None, extract_with_limit, str(input_path), str(temp_dir_path)
                )
            except ValueError as e:
                logger.warning(f"[unzip] {e}")
                await matcher.finish(f"解压被拒绝：请反馈bot主人")
            except zipfile.BadZipFile:
                logger.error("文件不是有效的 zip 压缩包")
                await matcher.finish("不支持的文件格式，仅能解压 zip/osz/mcz")

            if not extracted_files:
                logger.error("[unzip] 压缩包内无文件")
                await matcher.finish("压缩包为空")

            # 5. 发送所有解压出来的文件（保持原静默发送逻辑）
            for f in sorted(extracted_files):
                try:
                    if isinstance(event, GroupMessageEvent):
                        await bot.upload_group_file(
                            group_id=event.group_id,
                            file=str(f.absolute()),
                            name=f.name
                        )
                    elif isinstance(event, PrivateMessageEvent):
                        await bot.upload_private_file(
                            user_id=event.user_id,
                            file=str(f.absolute()),
                            name=f.name
                        )
                except Exception:
                    pass  # 发送失败静默忽略

    except Exception as e:
        logger.error(f"[unzip] 出错: {e}")
        await matcher.finish()
# ---- 为不同命令绑定同一个处理函数 ----
@ma2om.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_conversion(ma2om, bot, event, "ma2om")

@mp32ogg.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_conversion(mp32ogg, bot, event, "mp32ogg")

@ncm2mp3.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_conversion(ncm2mp3, bot, event, "ncm2mp3")

@ncm2ogg.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_conversion(ncm2ogg, bot, event, "ncm2ogg")


@toinverse.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    await _run_chart_tool(
        bot,
        event,
        toinverse,
        "toinverse",
        args.extract_plain_text(),
    )


@to_nk.handle()
async def _(bot: Bot, event: MessageEvent):
    # OneBot/NapCat 会把机器人自己发出的群消息再次投递给事件处理器。
    # 转换失败时的回复以 ``to5k/to6k ...`` 开头，不能再次被当成命令，
    # 否则“处理失败：请反馈bot主人”会被误当作 lambda 参数。
    event_user_id = getattr(event, "user_id", None)
    bot_self_id = getattr(bot, "self_id", None)
    if (
        event_user_id is not None
        and bot_self_id is not None
        and str(event_user_id) == str(bot_self_id)
    ):
        await to_nk.finish()

    command_text = event.get_plaintext().strip()
    parts = command_text.split()
    match = re.fullmatch(r"/?to([1-9]\d*)k", parts[0], flags=re.IGNORECASE) \
        if parts else None
    if not match:
        await to_nk.finish()

    target_columns = match.group(1)
    values = []
    ignore_ln = False
    global_hold_mapper = False
    for value in parts[1:]:
        if value.lower() in {"-i", "--ignoreln"}:
            if ignore_ln:
                await to_nk.finish("ignoreLN 参数只能指定一次。")
            ignore_ln = True
        elif value.lower() in {"-g", "--globalholdmapper"}:
            if global_hold_mapper:
                await to_nk.finish("globalHoldMapper 参数只能指定一次。")
            global_hold_mapper = True
        else:
            values.append(value)
    if len(values) > 2:
        await to_nk.finish(
        "用法：/toNk [lambda] [local_gap_scale] [--ignoreLN|-i]"
        " [--globalHoldMapper|-g]"
        )

    lambda_value = values[0] if values else "0"
    local_gap_scale = values[1] if len(values) > 1 else "0"
    numeric_argument = re.compile(r"(?:\d+(?:\.\d+)?|\d+/\d+)$")
    if not numeric_argument.fullmatch(lambda_value):
        await to_nk.finish("lambda 必须是非负数字，例如 0 或 0.5。")
    if not numeric_argument.fullmatch(local_gap_scale):
        await to_nk.finish("局部缩放参数必须是非负数字，例如 0、0.5 或 2。")

    command_name = f"to{target_columns}k"
    script_args = [target_columns, lambda_value, local_gap_scale]
    if ignore_ln:
        script_args.append("--ignoreLN")
    if global_hold_mapper:
        script_args.append("--globalHoldMapper")
    await _run_chart_tool(
        bot,
        event,
        to_nk,
        command_name,
        "",
        script_path_override=PRONTOM_EXE,
        script_args_override=tuple(script_args),
        output_suffix_override=f"_to{target_columns}K",
    )


@unzip_file.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_unzip(unzip_file, bot, event)
