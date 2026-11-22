from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from nonebot import logger, on_command, on_message
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule

from . import foreign_adapter
from .framework import platform_user_id
from .media import download_media, select_media, send_path


SOURCE_ROOT = Path("src/plugins/MalodyBakaRating/SourseChart")
KIND_PROMPT = "请提出该谱面的键型(叠，技，乱，切，混合)或者(jack,tech,speed,stream,mix)"
LEVEL_PROMPT = "请发送该谱面的难度(介于3-4dan之间则填写3，ex2-ex3之间则填写12)"
KIND_ALIASES = {
    "叠": "jack",
    "技": "tech",
    "乱": "speed",
    "切": "stream",
    "混合": "mix",
    "mix": "mix",
    "jack": "jack",
    "tech": "tech",
    "speed": "speed",
    "stream": "stream",
}
PENDING: dict[str, dict] = {}


def _key(bot: Bot, event: Event) -> str:
    return platform_user_id(bot, event) + ":" + str(
        getattr(event, "channel_id", getattr(getattr(event, "chat", None), "id", "private"))
    )


def _extract_mcz(path: Path, target: Path) -> bool:
    import zipfile

    try:
        root = target.resolve()
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                output = (target / member.filename).resolve()
                if not output.is_relative_to(root):
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, output.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        return True
    except Exception:
        return False


def _find_mc(target: Path) -> list[Path]:
    return sorted(
        path for path in target.rglob("*.mc") if path.is_file()
    )


def _kind(value: str) -> str | None:
    return KIND_ALIASES.get(value.strip().lower())


def _level(value: str) -> int | None:
    if not value.strip().isdigit():
        return None
    number = int(value)
    return number if 0 <= number <= 20 else None


submit = on_command(
    "提交谱面",
    aliases={"tc"},
    priority=5,
    block=True,
    rule=foreign_adapter,
)


@submit.handle()
async def handle_submit(bot: Bot, event: Event):
    media = select_media(event, suffixes=(".mcz",))
    if not media:
        await submit.finish("请发送或回复一个 .mcz 文件。")

    work_dir = Path(tempfile.mkdtemp(prefix="multiplatform_rating_"))
    source = work_dir / Path(media.name).name
    extract_dir = work_dir / "extract"
    extract_dir.mkdir()
    if not await download_media(bot, media, source):
        shutil.rmtree(work_dir, ignore_errors=True)
        await submit.finish("下载 .mcz 文件失败。")
    if not await asyncio.to_thread(_extract_mcz, source, extract_dir):
        shutil.rmtree(work_dir, ignore_errors=True)
        await submit.finish("无法解压 .mcz 文件。")
    charts = _find_mc(extract_dir)
    if len(charts) != 1:
        shutil.rmtree(work_dir, ignore_errors=True)
        await submit.finish("mcz 中必须且只能包含一个谱面。")
    try:
        import json

        data = json.loads(charts[0].read_text(encoding="utf-8-sig"))
        if int(data.get("meta", {}).get("mode_ext", {}).get("column", 0)) != 4:
            shutil.rmtree(work_dir, ignore_errors=True)
            await submit.finish("仅支持 4K 谱面。")
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        await submit.finish("无法读取谱面信息。")
    PENDING[_key(bot, event)] = {
        "stage": "kind",
        "work_dir": work_dir,
        "source": source,
        "name": source.name,
    }
    await submit.send(KIND_PROMPT)


async def _pending(bot: Bot, event: Event) -> bool:
    return bot.adapter.get_name() in {"Discord", "Telegram"} and _key(bot, event) in PENDING


pending_listener = on_message(
    rule=Rule(_pending),
    priority=6,
    block=True,
)


@pending_listener.handle()
async def handle_submit_step(bot: Bot, event: Event):
    key = _key(bot, event)
    state = PENDING.get(key)
    if not state:
        return
    text = event.get_plaintext().strip()
    if state["stage"] == "kind":
        value = _kind(text)
        if not value:
            shutil.rmtree(state["work_dir"], ignore_errors=True)
            PENDING.pop(key, None)
            await bot.send(event, "键型无效，提交已取消。")
            return
        state["kind"] = value
        state["stage"] = "level"
        await bot.send(event, LEVEL_PROMPT)
        return

    level = _level(text)
    if level is None:
        shutil.rmtree(state["work_dir"], ignore_errors=True)
        PENDING.pop(key, None)
        await bot.send(event, "难度无效，提交已取消。")
        return

    target_dir = SOURCE_ROOT / str(state["kind"]) / str(level)
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = target_dir / state["name"]
    shutil.copy2(state["source"], saved)
    await bot.send(event, f"提交成功，已保存为 {state['kind']}-{level}。")
    await send_path(bot, event, saved)
    shutil.rmtree(state["work_dir"], ignore_errors=True)
    PENDING.pop(key, None)
