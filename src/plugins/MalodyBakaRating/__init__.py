from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import httpx
from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import Arg
from nonebot.typing import T_State
from src.storage import plugin_data


PLUGIN_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = plugin_data("MalodyBakaRating") / "SourseChart"
QUEUE_GROUP_ID = 451586654

KIND_PROMPT = "请提出该谱面的键型(叠，技，乱，切，混合)或者(jack,tech,speed,stream,mix)"
LEVEL_PROMPT = "请发送该谱面的难度(介于3-4dan之间则填写3，ex2-ex3之间则填写12)"
CANCEL_MSG = "已取消"
SUCCESS_MSG = "提交成功"

KIND_ALIASES = {
    "叠": "jack",
    "技": "tech",
    "乱": "speed",
    "切": "stream",
    "mix": "mix",
    "jack": "jack",
    "tech": "tech",
    "speed": "speed",
    "stream": "stream",
}


tc = on_command("提交谱面", aliases={"tc"}, priority=5, block=True)


def _get_reply_file_segment(event: MessageEvent):
    if not event.reply:
        return None
    for seg in event.reply.message:
        if seg.type == "file":
            return seg
    return None


def _basename_from_any(raw: str) -> str:
    if not raw:
        return ""

    text = unquote(raw)
    if text.startswith("file:///"):
        text = text[8:]
    elif text.startswith("file://"):
        text = text[7:]

    return Path(text).name


def _as_local_path(raw: str) -> Optional[Path]:
    if not raw:
        return None

    text = unquote(raw)
    if text.startswith("file:///"):
        text = text[8:]
    elif text.startswith("file://"):
        text = text[7:]

    candidate = Path(text)
    if candidate.is_file():
        return candidate
    return None


def _cleanup_submission_state(state: T_State) -> None:
    work_dir = state.pop("work_dir", None)
    if work_dir:
        try:
            shutil.rmtree(Path(str(work_dir)), ignore_errors=True)
        except Exception as exc:
            logger.warning(f"[MalodyBakaRating] 清理工作目录失败: {exc}")

    for key in (
        "mcz_path",
        "mcz_name",
        "source_mc_path",
        "chart_kind",
        "chart_level",
        "stage",
    ):
        state.pop(key, None)


async def _resolve_reply_file_info(bot: Bot, event: MessageEvent) -> Optional[dict]:
    seg = _get_reply_file_segment(event)
    if seg is None:
        return None

    data = seg.data
    name = str(data.get("name") or data.get("filename") or data.get("file") or "")
    file_id = str(data.get("file_id") or "")
    url = str(data.get("url") or "")
    local_path = ""

    if file_id:
        try:
            file_data = await bot.get_file(file_id=file_id)
            url = url or str(file_data.get("url") or "")
            local_path = str(file_data.get("file") or "")
            if not name:
                name = _basename_from_any(local_path or url)
        except Exception as exc:
            logger.warning(f"[MalodyBakaRating] 获取回复文件信息失败: {exc}")

    if not name:
        name = _basename_from_any(local_path or url)

    if not name:
        return None

    return {
        "name": name,
        "file_id": file_id,
        "url": url,
        "local_path": local_path,
    }


async def _download_reply_file(bot: Bot, file_info: dict, dest: Path) -> bool:
    try:
        for candidate in (
            str(file_info.get("url") or ""),
            str(file_info.get("local_path") or ""),
        ):
            local_path = _as_local_path(candidate)
            if local_path is not None:
                shutil.copy2(local_path, dest)
                return True

        url = str(file_info.get("url") or "")
        if url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                return True

        file_id = str(file_info.get("file_id") or "")
        if file_id:
            try:
                file_data = await bot.get_file(file_id=file_id)
            except Exception as exc:
                logger.warning(f"[MalodyBakaRating] get_file 失败: {exc}")
            else:
                url = str(file_data.get("url") or "")
                local_path = str(file_data.get("file") or "")
                local_path_obj = _as_local_path(local_path)
                if local_path_obj is not None:
                    shutil.copy2(local_path_obj, dest)
                    return True
                if url.startswith(("http://", "https://")):
                    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        return True
                local_path_obj = _as_local_path(url)
                if local_path_obj is not None:
                    shutil.copy2(local_path_obj, dest)
                    return True

        fallback_path = _as_local_path(url)
        if fallback_path is not None:
            shutil.copy2(fallback_path, dest)
            return True
    except Exception as exc:
        logger.error(f"[MalodyBakaRating] 下载文件失败: {exc}")

    return False


def _extract_mcz_archive(mcz_path: Path, extract_dir: Path) -> bool:
    try:
        extract_root = extract_dir.resolve()
        with zipfile.ZipFile(mcz_path, "r") as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                target_path = (extract_dir / member.filename).resolve()
                try:
                    target_path.relative_to(extract_root)
                except ValueError:
                    logger.warning(
                        f"[MalodyBakaRating] 跳过越界条目: {member.filename}"
                    )
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        return True
    except zipfile.BadZipFile:
        logger.error(f"[MalodyBakaRating] 无效的 mcz 文件: {mcz_path}")
    except Exception as exc:
        logger.error(f"[MalodyBakaRating] 解压 mcz 失败: {exc}")
    return False


def _find_mc_files(extract_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in extract_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".mc"
    )


def _read_mc_column(mc_path: Path) -> tuple[bool, Optional[int]]:
    try:
        payload = json.loads(mc_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.error(f"[MalodyBakaRating] 解析 mc 失败: {mc_path} ({exc})")
        return False, None

    try:
        column_value = payload["meta"]["mode_ext"]["column"]
    except Exception:
        return True, None

    try:
        return True, int(column_value)
    except Exception:
        return True, None


def _normalize_kind(text: str) -> Optional[str]:
    raw = text.strip()
    if not raw:
        return None
    if raw in KIND_ALIASES:
        return KIND_ALIASES[raw]
    return KIND_ALIASES.get(raw.lower())


def _parse_level(text: str) -> Optional[int]:
    raw = text.strip()
    if not raw.isdecimal():
        return None
    value = int(raw)
    if 0 <= value <= 20:
        return value
    return None


@tc.handle()
async def handle_submit_first(bot: Bot, event: MessageEvent, state: T_State):
    file_info = await _resolve_reply_file_info(bot, event)
    if not file_info:
        return

    file_name = str(file_info["name"])
    if not file_name.lower().endswith(".mcz"):
        return

    work_dir = Path(tempfile.mkdtemp(prefix="malody_baka_rating_"))
    mcz_name = Path(file_name).name or "chart.mcz"
    mcz_path = work_dir / mcz_name
    extract_dir = work_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    state["work_dir"] = str(work_dir)
    state["mcz_path"] = str(mcz_path)
    state["mcz_name"] = mcz_name
    state["stage"] = "need_kind"

    logger.info(f"[MalodyBakaRating] 开始处理提交: {mcz_name}")

    if not await _download_reply_file(bot, file_info, mcz_path):
        logger.error(f"[MalodyBakaRating] 下载提交文件失败: {mcz_name}")
        _cleanup_submission_state(state)
        return

    extracted = await asyncio.to_thread(_extract_mcz_archive, mcz_path, extract_dir)
    if not extracted:
        _cleanup_submission_state(state)
        return

    mc_files = await asyncio.to_thread(_find_mc_files, extract_dir)
    if not mc_files:
        _cleanup_submission_state(state)
        await tc.finish("mcz中不存在谱面")

    if len(mc_files) > 1:
        logger.warning(
            f"[MalodyBakaRating] mcz 内找到多个谱面: {[str(path) for path in mc_files]}"
        )
        _cleanup_submission_state(state)
        await tc.finish("mcz中只能有一个谱面")

    mc_path = mc_files[0]
    state["source_mc_path"] = str(mc_path)

    ok, column = await asyncio.to_thread(_read_mc_column, mc_path)
    if not ok:
        _cleanup_submission_state(state)
        return

    if column != 4:
        _cleanup_submission_state(state)
        await tc.finish("仅支持4k谱面")

    await tc.send(KIND_PROMPT)


@tc.got("user_input")
async def handle_submit_step(bot: Bot, state: T_State, user_input: Message = Arg("user_input")):
    stage = str(state.get("stage") or "")
    text = user_input.extract_plain_text().strip()

    if stage == "need_kind":
        kind = _normalize_kind(text)
        if not kind:
            _cleanup_submission_state(state)
            await tc.finish(CANCEL_MSG)

        state["chart_kind"] = kind
        state["stage"] = "need_level"
        await tc.reject(LEVEL_PROMPT)
        return

    elif stage == "need_level":
        level = _parse_level(text)
        if level is None:
            _cleanup_submission_state(state)
            await tc.finish(CANCEL_MSG)

        kind = str(state.get("chart_kind") or "")
        mcz_path = Path(str(state.get("mcz_path") or ""))
        mcz_name = str(state.get("mcz_name") or mcz_path.name or "chart.mcz")

        if not kind or not mcz_path.is_file():
            logger.error("[MalodyBakaRating] 状态异常，无法完成提交")
            _cleanup_submission_state(state)
            await tc.finish()

        target_dir = SOURCE_ROOT / kind / str(level)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            saved_path = target_dir / mcz_name
            shutil.copy2(mcz_path, saved_path)
        except Exception as exc:
            logger.error(f"[MalodyBakaRating] 保存谱面失败: {exc}")
            _cleanup_submission_state(state)
            await tc.finish()

        notify_text = f"待审队列有新的谱面:{kind}-{level}"
        try:
            await bot.upload_group_file(
                group_id=QUEUE_GROUP_ID,
                file=str(saved_path),
                name=saved_path.name,
            )
        except Exception as exc:
            logger.error(f"[MalodyBakaRating] 上传待审群文件失败: {exc}")

        try:
            await bot.send_group_msg(
                group_id=QUEUE_GROUP_ID,
                message=notify_text,
            )
        except Exception as exc:
            logger.error(f"[MalodyBakaRating] 发送待审群通知失败: {exc}")

        _cleanup_submission_state(state)
        await tc.finish(SUCCESS_MSG)

    else:
        logger.error(f"[MalodyBakaRating] 未知流程状态: {stage}")
        _cleanup_submission_state(state)
        await tc.finish()
