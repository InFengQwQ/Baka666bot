from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx
from nonebot import get_driver, logger, on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot_plugin_alconna import UniMessage

from . import foreign_adapter


def _send_image(image: bytes, *, name: str = "image.png"):
    """Send media through Alconna's existing adapter exporters."""
    return UniMessage.image(raw=image, name=name).send()


def _send_video(path: Path, *, name: str = "video.mp4"):
    return UniMessage.video(path=path, name=name).send()


# ---------------------------------------------------------------------------
# Basic portable commands
# ---------------------------------------------------------------------------

ping = on_command("ping", aliases={"测试"}, priority=10, block=True, rule=foreign_adapter)


@ping.handle()
async def handle_ping():
    await ping.finish("Pong! Baka666Bot 已准备就绪！")


# Help is provided for all adapters by the local Bakahelp plugin.


calacc = on_command(
    "calacc",
    aliases={"/calacc"},
    priority=10,
    block=True,
    rule=foreign_adapter,
)


@calacc.handle()
async def handle_calacc():
    await calacc.finish("https://uzxn.github.io/acc/")


# ---------------------------------------------------------------------------
# Bilibili parser
# ---------------------------------------------------------------------------

BILI_PATTERN = re.compile(
    r"(https?://)?(www\.)?bilibili\.com/video/((BV[0-9A-Za-z]+)|(av\d+))"
    r"|(https?://)?b23\.tv/[0-9A-Za-z]+"
)
PARSE_API = "https://api.bugpk.com/api/bilibili?url={url}"
TEMP_DIR = Path(tempfile.gettempdir()) / "nonebot_bili_parse"
TEMP_DIR.mkdir(exist_ok=True)


def _extract_bili_url(text: str) -> Optional[str]:
    match = BILI_PATTERN.search(text)
    return match.group() if match else None


async def _fetch_bili_info(url: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(PARSE_API.format(url=url))
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 200:
            logger.warning("Bilibili parser returned an error: {}", data)
            return None
        return data.get("data")
    except Exception as exc:
        logger.error("Bilibili parser request failed: {}", exc)
        return None


async def _download_video(video_url: str, title: str) -> Optional[Path]:
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:30] or "bilibili_video"
    path = TEMP_DIR / f"{safe_title}_{os.urandom(4).hex()}.mp4"
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", video_url) as response:
                response.raise_for_status()
                with path.open("wb") as file:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        file.write(chunk)
        return path
    except Exception as exc:
        logger.error("Bilibili video download failed: {}", exc)
        path.unlink(missing_ok=True)
        return None


parse_cmd = on_command(
    "解析",
    aliases={"parse"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@parse_cmd.handle()
async def handle_parse(args: Message = CommandArg()):
    url = _extract_bili_url(args.extract_plain_text().strip())
    if not url:
        await parse_cmd.finish("没有找到 Bilibili 视频链接。")
    if not url.startswith("http"):
        url = "https://" + url

    data = await _fetch_bili_info(url)
    if not data:
        await parse_cmd.finish("获取 Bilibili 视频信息失败。")

    title = data.get("title", "bilibili_video")
    videos = data.get("videos") or []
    video_url = videos[0].get("url") if videos else data.get("url")
    if not video_url:
        await parse_cmd.finish("没有找到可下载的视频地址。")

    path = await _download_video(video_url, title)
    if not path:
        await parse_cmd.finish("视频下载失败。")
    try:
        try:
            await _send_video(path, name=f"{title[:40]}.mp4")
        except Exception as exc:
            logger.warning("Video attachment failed, falling back to URL: {}", exc)
            await parse_cmd.send(f"{title}\n{video_url}")
    finally:
        path.unlink(missing_ok=True)
    await parse_cmd.finish()


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

img_config = get_driver().config
POLLINATIONS_KEY = getattr(img_config, "pollinations_key", None)
IMAGE_COOLDOWN_SECONDS = 300
image_cooldown: dict[str, float] = {}


def _parse_image_args(text: str) -> tuple[str, dict]:
    parts = text.split()
    options = {
        "width": 512,
        "height": 512,
        "model": "flux",
        "seed": None,
        "negative": None,
        "nologo": True,
        "enhance": False,
        "private": False,
    }
    prompt_parts: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if not part.startswith("--"):
            prompt_parts.append(part)
            index += 1
            continue

        key = part[2:].lower()
        if key in {"width", "height", "model", "seed", "negative"}:
            if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                value = parts[index + 1]
                if key in {"width", "height", "seed"}:
                    try:
                        options[key] = int(value)
                    except ValueError:
                        pass
                else:
                    options[key] = value
                index += 2
                continue
        elif key in {"nologo", "enhance", "private"}:
            options[key] = True
        else:
            prompt_parts.append(part)
        index += 1
    return " ".join(prompt_parts), options


def _build_image_url(prompt: str, options: dict) -> str:
    params = [
        f"key={POLLINATIONS_KEY}",
        f"width={options['width']}",
        f"height={options['height']}",
        f"model={options['model']}",
        "nologo=true",
    ]
    if options["seed"] is not None:
        params.append(f"seed={options['seed']}")
    if options["negative"]:
        params.append(f"negative={quote(options['negative'], safe='')}")
    if options["enhance"]:
        params.append("enhance=true")
    if options["private"]:
        params.append("private=true")
    return f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}?" + "&".join(params)


image_help = on_command(
    "生图帮助",
    aliases={"绘图帮助"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@image_help.handle()
async def handle_image_help():
    await image_help.finish(
        "/生图 <提示词> [--width 宽度] [--height 高度] [--model 模型] "
        "[--seed 种子] [--negative 负面词] [--enhance]"
    )


image_command = on_command(
    "生图",
    aliases={"生成图片", "画图"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@image_command.handle()
async def handle_image(event: Event, args: Message = CommandArg()):
    if not POLLINATIONS_KEY:
        await image_command.finish("未配置 POLLINATIONS_KEY。")

    user_id = event.get_user_id()
    superusers = {str(value) for value in get_driver().config.superusers}
    is_superuser = str(user_id) in superusers
    if not is_superuser:
        remaining = IMAGE_COOLDOWN_SECONDS - (
            time.time() - image_cooldown.get(str(user_id), 0)
        )
        if remaining > 0:
            await image_command.finish(f"冷却中，请等待 {int(remaining)} 秒后再试。")

    prompt, options = _parse_image_args(args.extract_plain_text().strip())
    if not prompt:
        await image_command.finish("提示词不能为空，请发送 /生图帮助 查看用法。")

    await image_command.send("正在生成图片，请稍候...")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(_build_image_url(prompt, options))
        if response.status_code == 200:
            if not is_superuser:
                image_cooldown[str(user_id)] = time.time()
            await _send_image(response.content)
        elif response.status_code == 401:
            await image_command.send("Key 无效。")
        elif response.status_code == 402:
            await image_command.send("余额不足。")
        elif response.status_code == 429:
            await image_command.send("请求频繁，请稍后再试。")
        else:
            await image_command.send(f"图片服务返回 HTTP {response.status_code}。")
    except httpx.TimeoutException:
        await image_command.send("图片生成超时。")
    except Exception as exc:
        logger.exception("Cross-platform image generation failed: {}", exc)
        await image_command.send("图片生成失败，请稍后再试。")
    await image_command.finish()


# ---------------------------------------------------------------------------
# Malody image commands. The existing drawing/fetching modules are reused,
# while their QQ-only matchers remain untouched and are not called here.
# ---------------------------------------------------------------------------

try:
    from ..Malody_new_chart.draw_new_chart import (
        draw_charts_grid,
        draw_new_chart_card,
        fetch_charts_range,
    )
except ImportError:
    draw_charts_grid = draw_new_chart_card = fetch_charts_range = None


new_chart = on_command(
    "新谱速递",
    priority=10,
    block=True,
    rule=foreign_adapter,
)


@new_chart.handle()
async def handle_new_chart(args: Message = CommandArg()):
    if not fetch_charts_range:
        await new_chart.finish("新谱速递模块不可用。")
    values = [int(value) for value in re.findall(r"\d+", args.extract_plain_text())]
    start = max(values[0], 1) if values else 1
    end = max(values[1], start) if len(values) > 1 else start
    try:
        charts = await fetch_charts_range(start, end)
        if not charts:
            await new_chart.finish("没有找到符合条件的谱面。")
        image = (
            await draw_new_chart_card(charts[0])
            if len(charts) == 1
            else await draw_charts_grid(charts, max_cols=4)
        )
        await _send_image(image)
    except Exception as exc:
        logger.exception("Cross-platform new chart command failed: {}", exc)
        await new_chart.finish("谱面图片生成失败。")
    await new_chart.finish()


try:
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'malody_rank')
    fetch_chart_page = _native_peer.fetch_chart_page
    fetch_chart_ranking = _native_peer.fetch_chart_ranking
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'malody_rank_draw')
    draw_malody_rank = _native_peer.draw_malody_rank
except ImportError:
    fetch_chart_page = fetch_chart_ranking = draw_malody_rank = None


rank = on_command("rank", priority=10, block=True, rule=foreign_adapter)


@rank.handle()
async def handle_rank(args: Message = CommandArg()):
    if not fetch_chart_page:
        await rank.finish("Malody 排行榜模块不可用。")
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await rank.finish("格式：/rank <cid> [mode(0-7)]")
    cid_text = parts[0][1:] if parts[0].lower().startswith("c") else parts[0]
    if not cid_text.isdigit():
        await rank.finish("请输入有效谱面 ID。")
    cid = int(cid_text)
    mode = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    mode = mode if 0 <= mode <= 7 else 0
    mode_name = {
        0: "Key",
        1: "Step",
        2: "DJ",
        3: "Catch",
        4: "Pad",
        5: "Taiko",
        6: "Ring",
        7: "Slide",
    }[mode]
    try:
        page = await fetch_chart_page(cid)
        api_records = await fetch_chart_ranking(cid, mode)
        if not page["web_records"] and not api_records:
            await rank.finish("无数据。")
        api_map = {record["ranking"]: record for record in (api_records or [])}
        merged = []
        for index, web in enumerate(page["web_records"]):
            ranking = index + 1
            api = api_map.get(ranking, {})
            merged.append(
                {
                    "uid": api.get("uid", web.get("uid", "")),
                    "username": api.get("username", web.get("username", "?")),
                    "avatar_url": web.get("avatar_url")
                    or f"https://cni.machart.top/avatar/{api.get('uid')}!avatar",
                    "score": api.get("score", 0),
                    "acc": api.get("acc", web.get("acc", 0)),
                    "combo": api.get("combo", web.get("combo", 0)),
                    "best": api.get("best"),
                    "cool": api.get("cool"),
                    "good": api.get("good"),
                    "miss": api.get("miss"),
                    "fc": api.get("fc", False),
                    "mod_icons": web.get("mod_icons", []),
                    "time": web.get("time", ""),
                    "acc_color": web.get("acc_color", ""),
                    "ranking": ranking,
                }
            )
        info = {
            "title": page.get("title", ""),
            "artist": page.get("artist", ""),
            "creator": page.get("creator", ""),
            "mode_text": page.get("mode_text", mode_name),
            "level": page.get("level", ""),
            "length": page.get("length", ""),
            "bpm": page.get("bpm", ""),
            "sid": page.get("sid", ""),
            "cid": cid,
            "cover_url": page.get("cover_url", ""),
        }
        await _send_image(await draw_malody_rank(info, mode_name, merged))
    except Exception as exc:
        logger.exception("Cross-platform Malody rank command failed: {}", exc)
        await rank.finish("排行榜图片生成失败。")
    await rank.finish()


try:
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'malody_search_chart')
    get_song_detail = _native_peer.get_song_detail
    render_song_image = _native_peer.render_song_image
    search_song = _native_peer.search_song
except ImportError:
    get_song_detail = render_song_image = search_song = None


search_chart = on_command(
    "sm",
    aliases={"搜歌"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@search_chart.handle()
async def handle_search_chart(args: Message = CommandArg()):
    if not search_song:
        await search_chart.finish("Malody 搜歌模块不可用。")
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await search_chart.finish("请提供歌曲关键词。")
    sid_match = re.fullmatch(r"[sS]\s*(\d+)", keyword)
    sid = int(sid_match.group(1)) if sid_match else await search_song(keyword)
    if not sid:
        await search_chart.finish("未找到匹配的歌曲。")
    try:
        image = await render_song_image(await get_song_detail(sid))
        await _send_image(image)
    except Exception as exc:
        logger.exception("Cross-platform Malody search command failed: {}", exc)
        await search_chart.finish("歌曲图片生成失败。")
    await search_chart.finish()


try:
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_toolkit', 'malody_top100')
    draw_global_top100 = _native_peer.draw_global_top100
    draw_mm_top100 = _native_peer.draw_mm_top100
    fetch_mm_top100 = _native_peer.fetch_mm_top100
    merge_top100 = _native_peer.merge_top100
except ImportError:
    draw_global_top100 = draw_mm_top100 = fetch_mm_top100 = merge_top100 = None


exptop = on_command("exptop", priority=10, block=True, rule=foreign_adapter)
mmtop = on_command("mmtop", priority=10, block=True, rule=foreign_adapter)


@exptop.handle()
async def handle_exptop():
    if not merge_top100:
        await exptop.finish("Malody 全球排行榜模块不可用。")
    try:
        records = await merge_top100()
        if not records:
            await exptop.finish("无数据。")
        await _send_image(await draw_global_top100(records))
    except Exception as exc:
        logger.exception("Cross-platform experience leaderboard failed: {}", exc)
        await exptop.finish("排行榜图片生成失败。")
    await exptop.finish()


@mmtop.handle()
async def handle_mmtop():
    if not fetch_mm_top100:
        await mmtop.finish("Malody MM 排行榜模块不可用。")
    try:
        records = await fetch_mm_top100()
        if not records:
            await mmtop.finish("无数据。")
        await _send_image(await draw_mm_top100(records))
    except Exception as exc:
        logger.exception("Cross-platform MM leaderboard failed: {}", exc)
        await mmtop.finish("排行榜图片生成失败。")
    await mmtop.finish()
