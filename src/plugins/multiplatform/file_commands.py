from __future__ import annotations

from src.plugin_runtime import tool_path

import asyncio
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from nonebot import logger, on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.params import CommandArg

from . import foreign_adapter
from .media import download_media, select_media, send_path


async def _download_selected(
    bot: Bot, event: Event, destination: Path, suffixes: tuple[str, ...]
):
    media = select_media(event, suffixes=suffixes)
    if not media:
        return None
    if not await download_media(bot, media, destination):
        return None
    return media


async def _send_outputs(bot: Bot, event: Event, directory: Path):
    outputs = [path for path in directory.rglob("*") if path.is_file()]
    for path in sorted(outputs):
        await send_path(bot, event, path)


def _conversion_config():
    try:
        from src.plugin_runtime import import_plugin_module
        _native_peer = import_plugin_module('Malody_toolkit', 'ma2om')
        CONFIGS = _native_peer.CONFIGS

        return CONFIGS
    except Exception:
        return {
            "ma2om": {
                "exe": str(tool_path("ma2om.exe")),
                "exts": (".mc", ".mcz", ".osz", ".zip"),
            },
            "mp32ogg": {
                "exe": str(tool_path("mp32ogg.exe")),
                "exts": (".mp3",),
            },
            "ncm2mp3": {
                "exe": str(tool_path("ncm2mp3.exe")),
                "exts": (".ncm",),
            },
            "ncm2ogg": {
                "exe": str(tool_path("ncm2ogg.exe")),
                "exts": (".ncm",),
            },
        }


async def _run_conversion(bot: Bot, event: Event, tool_key: str):
    config = _conversion_config()[tool_key]
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        media = select_media(event, suffixes=tuple(config["exts"]))
        if not media:
            await bot.send(event, f"请发送或回复 {config['exts']} 文件。")
            return
        input_path = work / Path(media.name).name
        if not await download_media(bot, media, input_path):
            await bot.send(event, "文件下载失败。")
            return
        if tool_key == "ma2om":
            from src.plugin_runtime import import_plugin_module

            converter = import_plugin_module("Malody_toolkit", "ma2om")
            try:
                output = await converter.convert_malody_to_osu(input_path)
            except Exception as exc:
                logger.exception("Malody to osu!mania conversion failed")
                await bot.send(event, "转换失败：请检查谱面文件后重试。")
                return
            await send_path(bot, event, output)
            return
        executable = Path(config["exe"])
        if not executable.exists():
            await bot.send(event, f"找不到转换工具：{executable}")
            return
        before = set(work.iterdir())
        process = await asyncio.create_subprocess_exec(
            str(executable),
            str(input_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work),
        )
        stdout, stderr = await process.communicate()
        outputs = [
            item
            for item in work.iterdir()
            if item not in before and item.is_file()
        ]
        if process.returncode != 0 or not outputs:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
            await bot.send(event, f"转换失败：{detail or '工具未生成输出文件'}")
            return
        for output in outputs:
            await send_path(bot, event, output)


def _conversion_matcher(name: str, aliases: set[str] | None = None):
    return on_command(
        name,
        aliases=aliases or set(),
        priority=5,
        block=True,
        rule=foreign_adapter,
    )


ma2om = _conversion_matcher("ma2om", {"ma2osu", "mc2osu", "mc2om"})
mp32ogg = _conversion_matcher("mp32ogg")
ncm2mp3 = _conversion_matcher("ncm2mp3")
ncm2ogg = _conversion_matcher("ncm2ogg")


@ma2om.handle()
async def handle_ma2om(bot: Bot, event: Event):
    await _run_conversion(bot, event, "ma2om")


@mp32ogg.handle()
async def handle_mp32ogg(bot: Bot, event: Event):
    await _run_conversion(bot, event, "mp32ogg")


@ncm2mp3.handle()
async def handle_ncm2mp3(bot: Bot, event: Event):
    await _run_conversion(bot, event, "ncm2mp3")


@ncm2ogg.handle()
async def handle_ncm2ogg(bot: Bot, event: Event):
    await _run_conversion(bot, event, "ncm2ogg")


unzip_command = _conversion_matcher("解压", {"unzip"})


@unzip_command.handle()
async def handle_unzip(bot: Bot, event: Event):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "archive.zip"
        media = select_media(event, suffixes=(".zip", ".osz", ".mcz"))
        if not media or not await download_media(bot, media, source):
            await unzip_command.finish("请发送或回复 zip、osz 或 mcz 文件。")
        output = root / "out"
        output.mkdir()
        total_size = 0
        total_files = 0
        try:
            with zipfile.ZipFile(source) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    total_files += 1
                    total_size += member.file_size
                    target = (output / member.filename).resolve()
                    if (
                        total_files > 500
                        or total_size > 100 * 1024 * 1024
                        or not target.is_relative_to(output.resolve())
                    ):
                        raise ValueError("压缩包超过安全限制或包含非法路径")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source_file, target.open("wb") as target_file:
                        shutil.copyfileobj(source_file, target_file)
        except (zipfile.BadZipFile, ValueError) as exc:
            await unzip_command.finish(f"解压失败：请反馈bot主人")
        await _send_outputs(bot, event, output)


speed_command = _conversion_matcher("倍速")
pitch_speed_command = _conversion_matcher("倍速变调")


async def _handle_speed_command(
    bot: Bot,
    event: Event,
    matcher,
    command_prefix: str,
    audio_processor,
    args: Message,
):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', '')
    mcz_speed = _native_peer.mcz_speed

    text = f"{command_prefix} {args.extract_plain_text()}".strip()
    try:
        reference_token, rate_tokens = mcz_speed._split_speed_command(
            text, command_prefix
        )
        rates = mcz_speed._parse_rate_tokens(rate_tokens, command_prefix)
    except ValueError as exc:
        await matcher.finish(str(exc))

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        media = select_media(event, suffixes=mcz_speed.CHART_INPUT_SUFFIXES)
        reference = (
            mcz_speed._parse_chart_reference(reference_token)
            if reference_token
            else None
        )
        if reference_token and reference is None:
            await matcher.finish(
                "无法识别谱面来源，请使用 bid、cid、sid 或有效的谱面链接。"
            )
        if media and reference is not None:
            await matcher.finish("请在文件附件和谱面链接之间选择一个来源。")
        if not media and reference is None:
            await matcher.finish(
                "请发送或回复 .osu、.osz、.mc、.mcz 文件，或提供 bid、cid、sid、谱面链接。"
            )

        try:
            if media is not None:
                input_path = root / Path(media.name).name
                if not await download_media(bot, media, input_path):
                    await matcher.finish("下载谱面文件失败。")
            else:
                input_path = await mcz_speed._download_chart_reference(reference, root)

            output = await mcz_speed._process_chart_input(
                input_path,
                root,
                rates,
                audio_processor,
            )
            await send_path(bot, event, output)
        except Exception as exc:
            logger.opt(exception=exc).error("Cross-platform speed command failed")
            await matcher.finish(f"倍速处理失败：请反馈bot主人")


@speed_command.handle()
async def handle_speed(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', '')
    mcz_speed = _native_peer.mcz_speed

    await _handle_speed_command(
        bot,
        event,
        speed_command,
        mcz_speed.COMMAND_PREFIX,
        mcz_speed._run_ffmpeg_atempo,
        args,
    )


@pitch_speed_command.handle()
async def handle_pitch_speed(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', '')
    mcz_speed = _native_peer.mcz_speed

    await _handle_speed_command(
        bot,
        event,
        pitch_speed_command,
        mcz_speed.PITCH_SPEED_COMMAND_PREFIX,
        mcz_speed._run_ffmpeg_speed_pitch,
        args,
    )


om2ma = _conversion_matcher("om2ma", {"osu2mc", "osu2ma", "om2mc"})


@om2ma.handle()
async def handle_om2ma(bot: Bot, event: Event):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'om2ma')

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        media = select_media(event, suffixes=(".osu", ".osz", ".zip"))
        if not media:
            await om2ma.finish("请发送或回复 .osu、.osz 或 .zip 文件。")
        source = root / Path(media.name).name
        if not await download_media(bot, media, source):
            await om2ma.finish("下载 .osu 文件失败。")
        try:
            output = await _native_peer.convert_osu_to_malody(source)
            await send_path(bot, event, output)
        except Exception as exc:
            logger.exception("osu!mania to Malody conversion failed")
            await om2ma.finish("转换失败：请检查谱面和音频文件后重试。")


mrv2mr = _conversion_matcher("mrv2mr")


@mrv2mr.handle()
async def handle_mrv2mr(bot: Bot, event: Event):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        media = select_media(event, suffixes=(".mrv",))
        if not media:
            await mrv2mr.finish("请发送或回复 .mrv 文件。")
        from src.plugin_runtime import import_plugin_module
        _native_peer = import_plugin_module('Malody_toolkit', 'mrv2mr')
        convert_mrv_to_mr = _native_peer.convert_mrv_to_mr

        source = root / Path(media.name).name
        if not await download_media(bot, media, source):
            await mrv2mr.finish("下载 .mrv 文件失败。")
        output = root / f"{source.stem}.mr"
        try:
            ok = await asyncio.to_thread(convert_mrv_to_mr, str(source), str(output))
        except Exception as exc:
            await mrv2mr.finish(f"转换出错：请反馈bot主人")
        if not ok or not output.exists():
            await mrv2mr.finish("转换失败，文件可能无效。")
        await send_path(bot, event, output)


level = _conversion_matcher("level", {"lv"})


@level.handle()
async def handle_level(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'LevelPredict.level')
    POSTPROCESS_ENABLED = _native_peer.POSTPROCESS_ENABLED
    extract_mcz_archive = _native_peer.extract_mcz_archive
    format_level = _native_peer.format_level
    postprocess_level = _native_peer.postprocess_level
    run_predict_script = _native_peer.run_predict_script

    media = select_media(event, suffixes=(".mc", ".mcz"))
    if not media:
        return
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / Path(media.name).name
        if not await download_media(bot, media, source):
            await level.finish("文件下载失败。")
        target = source
        if source.suffix.lower() == ".mcz":
            extracted = root / "mcz_input"
            extracted.mkdir()
            if not extract_mcz_archive(source, extracted):
                await level.finish("压缩包中没有找到 .mc 文件。")
            target = extracted
        results = await run_predict_script(target)
        if results is None:
            await level.finish("难度预测失败。")
        raw = args.extract_plain_text().strip().lower()
        use_postprocess = POSTPROCESS_ENABLED and raw not in {"raw", "off", "--raw", "--no-post"}
        values = []
        for item in results:
            value = float(item["level"])
            if use_postprocess:
                value = postprocess_level(value)
            values.append(f"{item.get('file', 'unknown.mc')}: {format_level(value)}级，仅供参考")
        await level.finish("\n".join(values) or "没有预测结果。")


download = _conversion_matcher("download")


@download.handle()
async def handle_download(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', '')
    malody_download = _native_peer.malody_download

    raw = args.extract_plain_text().strip()
    if len(raw) < 2 or raw[0].lower() not in {"c", "s"} or not raw[1:].isdigit():
        await download.finish("格式：/download c<CID> 或 /download s<SID>")
    prefix, identifier = raw[0].lower(), raw[1:]
    temporary = Path(tempfile.mkdtemp(prefix="multiplatform_download_"))
    try:
        if prefix == "c":
            name = (
                await malody_download.fetch_song_name_from_chart(identifier)
                or f"chart_{identifier}"
            )
            cids = [identifier]
        else:
            cids = await malody_download.fetch_cids_from_sid(identifier)
            if not cids:
                await download.finish("没有找到该 SID 下的谱面。")
            name = (
                await malody_download.fetch_song_name_from_song(identifier)
                or f"song_{identifier}"
            )
        output = temporary / f"{malody_download.safe_filename(name)}.mcz"
        await malody_download.build_mcz(cids, output)
        await send_path(bot, event, output)
    except Exception as exc:
        logger.opt(exception=exc).error("Cross-platform Malody download failed")
        await download.finish(f"下载失败：请反馈bot主人")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


hepu = _conversion_matcher("合谱")


@hepu.handle()
async def handle_hepu(bot: Bot, event: Event):
    path = Path("src/plugins/Malody_toolkit/Malody合谱工具.html")
    if not path.exists():
        await hepu.finish("合谱工具文件不存在。")
    await send_path(bot, event, path)
