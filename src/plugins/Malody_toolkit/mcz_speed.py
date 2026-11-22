from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import unquote, urlparse

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.rule import Rule

from src.plugin_runtime import tool_path


COMMAND_PREFIX = "倍速"
PITCH_SPEED_COMMAND_PREFIX = "倍速变调"
MAX_RATE = 100.0
MAX_RATE_COUNT = 20
PITCH_SPEED_SAMPLE_RATE = 48000
CHART_FILE_SUFFIXES = (".osu", ".mc")
CHART_ARCHIVE_SUFFIXES = (".osz", ".mcz")
CHART_INPUT_SUFFIXES = CHART_FILE_SUFFIXES + CHART_ARCHIVE_SUFFIXES


@dataclass
class ChartPlan:
    mc_path: Path
    mc_output_path: Path
    data: dict
    audio_src_path: Optional[Path]
    audio_output_path: Optional[Path]
    audio_note_index: int
    audio_name: str
    audio_output_name: str


@dataclass(frozen=True)
class ChartReference:
    kind: str
    value: str
    name: str = ""


def _normalize_text(text: str) -> str:
    return text.strip().lstrip("/!／").strip()


def _extract_file_info(event: MessageEvent) -> Optional[dict]:
    messages = [getattr(event, "message", None)]
    reply = getattr(event, "reply", None)
    if reply is not None:
        messages.append(getattr(reply, "message", None))

    for message in messages:
        if not message:
            continue
        for seg in message:
            if seg.type != "file":
                continue
            data = seg.data
            name = (
                data.get("name")
                or data.get("filename")
                or data.get("file_name")
                or data.get("file")
                or ""
            )
            return {
                "name": str(name).strip(),
                "file_id": data.get("file_id") or data.get("id"),
                "url": data.get("url") or data.get("file") or "",
            }
    return None


_extract_reply_file_info = _extract_file_info


def _onebot_command_rule(event: MessageEvent) -> bool:
    return isinstance(event, (GroupMessageEvent, PrivateMessageEvent))


def _parse_rate_token(token: str, command_prefix: str) -> float:
    payload = token.strip()
    if payload[:1] in {"x", "X", "*", "×"}:
        payload = payload[1:].strip()
    if payload[-1:] in {"x", "X", "*", "×"}:
        payload = payload[:-1].strip()

    if not re.fullmatch(r"(?:\d+(?:\.\d+)?|\.\d+)", payload):
        raise ValueError(
            f"倍速必须是大于 0 的数字，例如：{command_prefix} 1.1 1.5"
        )

    rate = round(float(payload), 6)
    if rate <= 0:
        raise ValueError("倍速必须大于 0")
    if rate > MAX_RATE:
        raise ValueError("倍速最大只能到 100")
    return rate


def _parse_rate_tokens(tokens: list[str], command_prefix: str) -> list[float]:
    if not tokens:
        raise ValueError(
            f"请输入倍速数值，例如：{command_prefix} 2 或 {command_prefix} 1.1 1.5"
        )
    if len(tokens) > MAX_RATE_COUNT:
        raise ValueError(f"一次最多只能生成 {MAX_RATE_COUNT} 个倍率版本")

    rates: list[float] = []
    for token in tokens:
        rate = _parse_rate_token(token, command_prefix)
        if rate not in rates:
            rates.append(rate)
    return rates


def _parse_rates_from_text(text: str, command_prefix: str = COMMAND_PREFIX) -> list[float]:
    normalized = _normalize_text(text)
    if not normalized.startswith(command_prefix):
        raise ValueError(f"请使用“{command_prefix} 数值”格式。")
    payload = normalized[len(command_prefix) :].strip()
    return _parse_rate_tokens(payload.split(), command_prefix)


def _looks_like_reference_token(token: str) -> bool:
    value = token.strip().strip("<>")
    if not value:
        return False
    if re.match(r"^https?://", value, re.IGNORECASE) or value.lower().startswith(
        "www."
    ):
        return True
    return bool(
        re.fullmatch(r"(?i)(?:bid|b|cid|c|sid|s)[:=]?\d+", value)
        or value.lower() in {"bid", "b", "cid", "c", "sid", "s"}
    )


def _split_speed_command(
    text: str, command_prefix: str = COMMAND_PREFIX
) -> tuple[Optional[str], list[str]]:
    normalized = _normalize_text(text)
    if not normalized.startswith(command_prefix):
        raise ValueError(f"请使用“{command_prefix} 数值”格式。")

    tokens = normalized[len(command_prefix) :].strip().split()
    reference: Optional[str] = None
    rate_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if reference is None and _looks_like_reference_token(token):
            clean = token.strip().strip("<>")
            if clean.lower() in {"bid", "b", "cid", "c", "sid", "s"}:
                if index + 1 >= len(tokens) or not tokens[index + 1].isdigit():
                    raise ValueError("ID 格式错误，例如：bid123、cid123 或 sid123")
                clean += tokens[index + 1]
                index += 1
            reference = clean
        else:
            rate_tokens.append(token)
        index += 1
    return reference, rate_tokens


def _parse_rate_from_text(text: str, command_prefix: str = COMMAND_PREFIX) -> float:
    rates = _parse_rates_from_text(text, command_prefix)
    if len(rates) != 1:
        raise ValueError(f"请只输入一个倍速数值：{command_prefix} 1.5")
    return rates[0]


def _parse_chart_reference(value: str) -> Optional[ChartReference]:
    value = value.strip().strip("<>")
    if not value:
        return None

    match = re.fullmatch(r"(?i)(?:cid|c)[:=]?(\d+)", value)
    if match:
        return ChartReference("malody_cid", match.group(1), f"chart_{match.group(1)}.mcz")
    match = re.fullmatch(r"(?i)(?:sid|s)[:=]?(\d+)", value)
    if match:
        return ChartReference("malody_sid", match.group(1), f"song_{match.group(1)}.mcz")

    osu_reference = _parse_osu_reference(value)
    if osu_reference:
        return ChartReference("url", osu_reference[0], osu_reference[1])

    if value.lower().startswith("www."):
        value = f"https://{value}"
    if re.match(r"https?://", value, re.IGNORECASE):
        parsed = urlparse(value)
        host = parsed.netloc.lower().split(":", 1)[0]
        path_parts = [part for part in unquote(parsed.path).split("/") if part]
        if host.endswith("mugzone.net") and len(path_parts) >= 2:
            if path_parts[0].lower() == "chart" and path_parts[1].isdigit():
                cid = path_parts[1]
                return ChartReference("malody_cid", cid, f"chart_{cid}.mcz")
            if path_parts[0].lower() == "song" and path_parts[1].isdigit():
                sid = path_parts[1]
                return ChartReference("malody_sid", sid, f"song_{sid}.mcz")

        suffix = Path(parsed.path).suffix.lower()
        if suffix in CHART_INPUT_SUFFIXES:
            return ChartReference("url", value, Path(parsed.path).name)
        return None
    return None


def _parse_osu_reference(value: str) -> Optional[tuple[str, str]]:
    value = value.strip().strip("<>")
    if not value:
        return None

    if re.fullmatch(r"(?i)(?:bid\s*[:=]?\s*|b\s*)?\d+", value):
        beatmap_id = re.search(r"\d+", value).group()
        return f"https://osu.ppy.sh/osu/{beatmap_id}", f"beatmap_{beatmap_id}.osu"

    if value.lower().startswith("www.osu.ppy.sh/"):
        value = f"https://{value}"
    if not re.match(r"https?://", value, re.IGNORECASE):
        return None

    parsed = urlparse(value)
    path = unquote(parsed.path).rstrip("/")
    path_parts = [part for part in path.split("/") if part]
    host = parsed.netloc.lower().split(":", 1)[0]
    if not host.endswith("osu.ppy.sh"):
        return None

    if len(path_parts) >= 2 and path_parts[0] in {"b", "beatmaps", "beatmap"}:
        if path_parts[1].isdigit():
            beatmap_id = path_parts[1]
            return (
                f"https://osu.ppy.sh/osu/{beatmap_id}",
                f"beatmap_{beatmap_id}.osu",
            )
    if len(path_parts) >= 2 and path_parts[0] == "osu":
        if path_parts[1].isdigit():
            beatmap_id = path_parts[1]
            return (
                f"https://osu.ppy.sh/osu/{beatmap_id}",
                f"beatmap_{beatmap_id}.osu",
            )

    if path_parts and path_parts[0] == "beatmapsets" and len(path_parts) >= 2:
        for part in reversed(parsed.fragment.split("/")):
            if part.isdigit():
                return (
                    f"https://osu.ppy.sh/osu/{part}",
                    f"beatmap_{part}.osu",
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


def _format_decimal(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _speed_suffix(rate: float) -> str:
    return f"-{_format_decimal(rate)}x"


def _rename_with_suffix(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def _load_mc_data(mc_path: Path) -> dict:
    try:
        with mc_path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError:
        with mc_path.open("r", encoding="utf-8", errors="strict") as f:
            data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{mc_path.name} 不是有效的 .mc JSON 对象")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValueError(f"{mc_path.name} 缺少 meta 字段")

    notes = data.get("note")
    if not isinstance(notes, list) or not notes:
        raise ValueError(f"{mc_path.name} 缺少 note 数组")

    times = data.get("time")
    if not isinstance(times, list) or not times:
        raise ValueError(f"{mc_path.name} 缺少 time 数组")

    return data


def _find_audio_note(notes: list) -> tuple[int, str]:
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            continue
        note_type = note.get("type", 0)
        try:
            note_type_value = int(note_type)
        except Exception:
            note_type_value = 0
        if note_type_value == 0:
            continue
        sound = note.get("sound")
        if isinstance(sound, str) and sound.strip():
            sound_path = Path(sound.replace("\\", "/"))
            if sound_path.parent != Path("."):
                raise ValueError(f"音频文件必须与 .mc 同目录: {sound}")
            return index, sound_path.name
    raise ValueError("无法从 note 数组找到音频文件")


def _scale_chart_data(data: dict, rate: float, audio_note_index: int, new_audio_name: str) -> None:
    meta = data.get("meta")
    if isinstance(meta, dict):
        preview = meta.get("preview")
        if isinstance(preview, (int, float, str)):
            try:
                meta["preview"] = int(round(float(preview) / rate))
            except Exception:
                pass

        song = meta.get("song")
        if isinstance(song, dict):
            if isinstance(song.get("file"), str) and song["file"]:
                song["file"] = new_audio_name
            bpm = song.get("bpm")
            if isinstance(bpm, (int, float, str)):
                try:
                    scaled_bpm = round(float(bpm) * rate, 6)
                    song["bpm"] = int(round(scaled_bpm)) if scaled_bpm.is_integer() else scaled_bpm
                except Exception:
                    pass

    notes = data.get("note")
    if isinstance(notes, list) and 0 <= audio_note_index < len(notes):
        audio_note = notes[audio_note_index]
        if isinstance(audio_note, dict):
            audio_note["sound"] = new_audio_name
            offset = audio_note.get("offset")
            if isinstance(offset, (int, float, str)):
                try:
                    audio_note["offset"] = int(round(float(offset) / rate))
                except Exception:
                    pass

    times = data.get("time")
    if isinstance(times, list):
        bpm_found = False
        for item in times:
            if not isinstance(item, dict):
                continue
            bpm = item.get("bpm")
            if isinstance(bpm, (int, float, str)):
                try:
                    scaled_bpm = round(float(bpm) * rate, 6)
                    item["bpm"] = int(round(scaled_bpm)) if scaled_bpm.is_integer() else scaled_bpm
                    bpm_found = True
                except Exception:
                    pass

            delay = item.get("delay")
            if isinstance(delay, (int, float, str)):
                try:
                    item["delay"] = int(round(float(delay) / rate))
                except Exception:
                    pass

        if not bpm_found:
            raise ValueError("time 数组中没有可用的 bpm 字段")


def _append_rate_label(data: dict, rate: float) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        return
    label = f"{_format_decimal(rate)}x"
    version = str(meta.get("version") or "").strip()
    if version.endswith(label):
        return
    meta["version"] = f"{version} {label}".strip()


def _remove_mc_cid(value: object) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if str(key).casefold() == "cid":
                del value[key]
            else:
                _remove_mc_cid(value[key])
    elif isinstance(value, list):
        for item in value:
            _remove_mc_cid(item)


def _find_chart_files(work_dir: Path, suffix: str) -> list[Path]:
    return sorted(
        p for p in work_dir.rglob("*") if p.is_file() and p.suffix.lower() == suffix
    )


def _build_chart_plans(
    work_dir: Path,
    rate: float,
    mc_files: Optional[list[Path]] = None,
    *,
    require_audio: bool = True,
) -> list[ChartPlan]:
    mc_files = list(mc_files) if mc_files is not None else _find_chart_files(work_dir, ".mc")
    if not mc_files:
        raise ValueError("压缩包中没有找到 .mc 文件")

    suffix = _speed_suffix(rate)
    plans: list[ChartPlan] = []

    for mc_path in mc_files:
        data = _load_mc_data(mc_path)
        audio_note_index, audio_name = _find_audio_note(data["note"])
        audio_src_path = mc_path.parent / audio_name
        if not audio_src_path.exists():
            if require_audio:
                raise FileNotFoundError(f"{mc_path.name} 找不到对应的音频文件: {audio_name}")
            audio_src_path = None

        audio_output_name = (
            _rename_with_suffix(Path(audio_name), suffix).name
            if audio_src_path is not None
            else audio_name
        )
        audio_output_path = (
            mc_path.parent / audio_output_name if audio_src_path is not None else None
        )
        mc_output_path = _rename_with_suffix(mc_path, suffix)

        plans.append(
            ChartPlan(
                mc_path=mc_path,
                mc_output_path=mc_output_path,
                data=data,
                audio_src_path=audio_src_path,
                audio_output_path=audio_output_path,
                audio_note_index=audio_note_index,
                audio_name=audio_name,
                audio_output_name=audio_output_name,
            )
        )

    return plans


def _build_audio_jobs(plans: list[ChartPlan]) -> dict[Path, Path]:
    jobs: dict[Path, Path] = {}
    for plan in plans:
        if plan.audio_src_path is None or plan.audio_output_path is None:
            continue
        jobs.setdefault(plan.audio_src_path, plan.audio_output_path)
    return jobs


async def _run_ffmpeg_atempo(input_audio: Path, output_audio: Path, rate: float) -> None:
    factors: list[float] = []
    remaining = float(rate)
    while remaining > 2.0:
        factors.append(2.0)
        remaining = round(remaining / 2.0, 6)
    while remaining < 0.5:
        factors.append(0.5)
        remaining = round(remaining / 0.5, 6)
    factors.append(round(remaining, 6))

    filter_chain = ",".join(f"atempo={_format_decimal(value)}" for value in factors)
    await _run_ffmpeg_filter(input_audio, output_audio, filter_chain)


async def _run_ffmpeg_speed_pitch(
    input_audio: Path, output_audio: Path, rate: float
) -> None:
    filter_chain = (
        f"aformat=sample_rates={PITCH_SPEED_SAMPLE_RATE},"
        f"asetrate={PITCH_SPEED_SAMPLE_RATE}*{_format_decimal(rate)},"
        f"aresample={PITCH_SPEED_SAMPLE_RATE}"
    )
    await _run_ffmpeg_filter(input_audio, output_audio, filter_chain)


async def _run_ffmpeg_filter(
    input_audio: Path, output_audio: Path, filter_chain: str
) -> None:
    ffmpeg_exe = tool_path("ffmpeg.exe")
    if not ffmpeg_exe.is_file():
        raise RuntimeError("项目内未找到 Malody Toolkit 的 ffmpeg.exe")

    output_audio.parent.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        str(ffmpeg_exe),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_audio),
        "-vn",
        "-y",
        "-filter:a",
        filter_chain,
        str(output_audio),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or not output_audio.exists():
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr_text or stdout_text or f"ffmpeg 处理失败: {input_audio.name}")


def _write_scaled_chart(
    plan: ChartPlan, rate: float, *, append_rate_label: bool = True
) -> None:
    data = plan.data
    _scale_chart_data(data, rate, plan.audio_note_index, plan.audio_output_name)
    if append_rate_label:
        _append_rate_label(data, rate)
        _remove_mc_cid(data)

    plan.mc_output_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.mc_output_path.exists():
        plan.mc_output_path.unlink()
    with plan.mc_output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _repack_work_dir(work_dir: Path, output_mcz: Path) -> None:
    if output_mcz.exists():
        output_mcz.unlink()
    with zipfile.ZipFile(output_mcz, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(p for p in work_dir.rglob("*") if p.is_file()):
            archive.write(file_path, file_path.relative_to(work_dir).as_posix())


def _format_osu_number(value: float) -> str:
    rounded = round(value, 6)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.6f}".rstrip("0").rstrip(".")


def _scale_osu_number(token: str, rate: float) -> str:
    try:
        value = float(token.strip())
    except ValueError:
        return token
    return _format_osu_number(value / rate)


def _scale_osu_integer(token: str, rate: float) -> str:
    try:
        value = float(token.strip())
    except ValueError:
        return token
    return str(int(round(value / rate)))


def _extract_osu_audio_name(text: str) -> str:
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if section == "General" and stripped.startswith("AudioFilename:"):
            return stripped.partition(":")[2].strip().strip('"')
    return ""


def _resolve_osu_audio_path(
    osu_path: Path, audio_name: str, work_dir: Path
) -> Optional[Path]:
    if not audio_name:
        return None
    relative = Path(audio_name.replace("\\", "/"))
    if relative.is_absolute():
        return None
    candidate = (osu_path.parent / relative).resolve()
    if not candidate.is_relative_to(work_dir.resolve()):
        return None
    return candidate


def _scale_osu_text(
    text: str,
    rate: float,
    new_audio_name: Optional[str],
    *,
    append_rate_label: bool,
    remove_beatmap_ids: bool = False,
) -> str:
    section = ""
    output: list[str] = []
    label = f"{_format_decimal(rate)}x"

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            output.append(raw_line)
            continue
        if not stripped or stripped.startswith("//"):
            output.append(raw_line)
            continue

        if remove_beatmap_ids:
            key, separator, _ = raw_line.partition(":")
            if separator and key.strip().lower() == "beatmapid":
                continue

        if section == "General":
            key, separator, value = raw_line.partition(":")
            key_name = key.strip()
            if key_name == "AudioFilename" and new_audio_name:
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                output.append(f"{indent}AudioFilename: {new_audio_name}")
                continue
            if key_name in {"AudioLeadIn", "PreviewTime"} and separator:
                if value.strip().startswith("-") and key_name == "PreviewTime":
                    output.append(raw_line)
                else:
                    output.append(f"{key}: {_scale_osu_integer(value, rate)}")
                continue

        if section == "Metadata" and append_rate_label:
            key, separator, value = raw_line.partition(":")
            if key.strip() == "Version" and separator:
                version = value.strip()
                if not version.endswith(label):
                    version = f"{version} {label}".strip()
                output.append(f"{key}: {version}")
                continue

        if section == "Editor":
            key, separator, value = raw_line.partition(":")
            if key.strip() == "Bookmarks" and separator:
                bookmarks = ",".join(
                    _scale_osu_integer(item, rate) for item in value.split(",")
                )
                output.append(f"{key}: {bookmarks}")
                continue

        if section == "TimingPoints":
            parts = raw_line.split(",")
            if len(parts) >= 2:
                parts[0] = _scale_osu_number(parts[0], rate)
                parts[1] = _scale_osu_number(parts[1], rate)
                output.append(",".join(parts))
                continue

        if section == "HitObjects":
            parts = raw_line.split(",")
            if len(parts) >= 3:
                parts[2] = _scale_osu_integer(parts[2], rate)
            if len(parts) >= 6:
                try:
                    object_type = int(parts[3])
                except ValueError:
                    object_type = 0
                if object_type & 128:
                    extras = parts[5].split(":")
                    if extras and extras[0].strip():
                        extras[0] = _scale_osu_integer(extras[0], rate)
                    parts[5] = ":".join(extras)
            output.append(",".join(parts))
            continue

        if section == "Events":
            parts = raw_line.split(",")
            event_name = parts[0].strip().lower() if parts else ""
            if event_name == "2" and len(parts) >= 3:
                parts[1] = _scale_osu_integer(parts[1], rate)
                parts[2] = _scale_osu_integer(parts[2], rate)
                output.append(",".join(parts))
                continue
            if event_name == "video" and len(parts) >= 2:
                parts[1] = _scale_osu_integer(parts[1], rate)
                output.append(",".join(parts))
                continue
            if event_name == "break period" and len(parts) >= 3:
                parts[1] = _scale_osu_integer(parts[1], rate)
                parts[2] = _scale_osu_integer(parts[2], rate)
                output.append(",".join(parts))
                continue

        output.append(raw_line)

    result = "\n".join(output)
    return result + ("\n" if text.endswith(("\n", "\r")) else "")


async def _process_mcz_workspace(
    work_dir: Path,
    rates: list[float],
    audio_processor: Callable[[Path, Path, float], Awaitable[None]],
    *,
    require_audio: bool,
) -> None:
    multi_rate = len(rates) > 1
    source_mc_files = _find_chart_files(work_dir, ".mc")
    rates_to_generate = [
        rate for rate in rates if not (multi_rate and rate == 1.0)
    ]

    for rate in rates_to_generate:
        plans = await asyncio.to_thread(
            _build_chart_plans,
            work_dir,
            rate,
            source_mc_files,
            require_audio=require_audio,
        )
        audio_jobs = _build_audio_jobs(plans)
        for index, (audio_src, audio_dst) in enumerate(audio_jobs.items(), start=1):
            logger.info(
                f"[mcz_speed] 倍率 x{_format_decimal(rate)} 音频 "
                f"{index}/{len(audio_jobs)}: {audio_src.name} -> {audio_dst.name}"
            )
            await audio_processor(audio_src, audio_dst, rate)

        for plan in plans:
            _write_scaled_chart(plan, rate, append_rate_label=True)

        if not multi_rate:
            for plan in plans:
                plan.mc_path.unlink(missing_ok=True)
            for audio_src in audio_jobs:
                audio_src.unlink(missing_ok=True)


async def _process_osu_workspace(
    work_dir: Path,
    rates: list[float],
    audio_processor: Callable[[Path, Path, float], Awaitable[None]],
) -> None:
    source_osu_files = _find_chart_files(work_dir, ".osu")
    if not source_osu_files:
        raise ValueError("谱面包中没有找到 .osu 文件")

    multi_rate = len(rates) > 1
    rates_to_generate = [
        rate for rate in rates if not (multi_rate and rate == 1.0)
    ]

    for rate in rates_to_generate:
        chart_outputs: list[tuple[Path, Path, str, Optional[str]]] = []
        audio_jobs: dict[Path, Path] = {}
        for osu_path in source_osu_files:
            text = osu_path.read_text(encoding="utf-8-sig", errors="replace")
            audio_name = _extract_osu_audio_name(text)
            audio_src_path = _resolve_osu_audio_path(osu_path, audio_name, work_dir)
            if audio_src_path is not None and audio_src_path.exists():
                output_audio_relative = _rename_with_suffix(
                    Path(audio_name.replace("\\", "/")), _speed_suffix(rate)
                ).as_posix()
                audio_output_path = osu_path.parent / output_audio_relative
                audio_jobs.setdefault(audio_src_path, audio_output_path)
                new_audio_name: Optional[str] = output_audio_relative
            else:
                new_audio_name = None

            chart_outputs.append(
                (
                    osu_path,
                    _rename_with_suffix(osu_path, _speed_suffix(rate)),
                    text,
                    new_audio_name,
                )
            )

        for index, (audio_src, audio_dst) in enumerate(audio_jobs.items(), start=1):
            logger.info(
                f"[mcz_speed] 倍率 x{_format_decimal(rate)} 音频 "
                f"{index}/{len(audio_jobs)}: {audio_src.name} -> {audio_dst.name}"
            )
            await audio_processor(audio_src, audio_dst, rate)

        for _, output_path, text, new_audio_name in chart_outputs:
            output_path.write_text(
                _scale_osu_text(
                    text,
                    rate,
                    new_audio_name,
                    append_rate_label=True,
                    remove_beatmap_ids=True,
                ),
                encoding="utf-8",
            )

        if not multi_rate:
            for source_path, _, _, _ in chart_outputs:
                source_path.unlink(missing_ok=True)
            for audio_src in audio_jobs:
                audio_src.unlink(missing_ok=True)


async def _process_chart_input(
    input_path: Path,
    temp_root: Path,
    rates: list[float],
    audio_processor: Callable[[Path, Path, float], Awaitable[None]],
) -> Path:
    suffix = input_path.suffix.lower()
    if suffix not in CHART_INPUT_SUFFIXES:
        raise ValueError("只支持 .osu、.osz、.mc、.mcz 文件")

    if suffix in CHART_ARCHIVE_SUFFIXES:
        work_dir = temp_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_extract_mcz_archive, input_path, work_dir)
        if suffix == ".mcz":
            await _process_mcz_workspace(
                work_dir, rates, audio_processor, require_audio=True
            )
        else:
            await _process_osu_workspace(work_dir, rates, audio_processor)
        output_path = temp_root / input_path.name
        await asyncio.to_thread(_repack_work_dir, work_dir, output_path)
        return output_path

    work_dir = temp_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    staged_input = work_dir / input_path.name
    shutil.copyfile(input_path, staged_input)
    if suffix == ".mc":
        await _process_mcz_workspace(
            work_dir, rates, audio_processor, require_audio=False
        )
    else:
        await _process_osu_workspace(work_dir, rates, audio_processor)

    if len(rates) > 1:
        output_suffix = ".mcz" if suffix == ".mc" else ".osz"
        output_path = temp_root / f"{input_path.stem}{output_suffix}"
        await asyncio.to_thread(_repack_work_dir, work_dir, output_path)
        return output_path

    output_path = temp_root / _rename_with_suffix(
        input_path, _speed_suffix(rates[0])
    ).name
    generated_path = work_dir / output_path.name
    if not generated_path.exists():
        raise FileNotFoundError(f"未生成处理后的谱面文件: {generated_path.name}")
    shutil.copyfile(generated_path, output_path)
    return output_path


async def _download_file(bot: Bot, file_info: dict, dest: Path) -> bool:
    file_url = str(file_info.get("url", "") or "")
    file_id = str(file_info.get("file_id", "") or "")

    try:
        if file_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                return True

        if file_id:
            try:
                file_data = await bot.call_api("get_file", file_id=file_id)
                url = str(file_data.get("url", "") or "")
                local_path = str(file_data.get("file", "") or "")

                if url.startswith(("http://", "https://")):
                    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        return True

                if local_path and Path(local_path).is_file():
                    shutil.copy(local_path, dest)
                    return True
            except Exception as e:
                logger.warning(f"[mcz_speed] get_file API 失败: {e}")

        if file_url and Path(file_url).is_file():
            shutil.copy(file_url, dest)
            return True

    except Exception as e:
        logger.error(f"[mcz_speed] 下载文件失败: {e}")

    return False


async def _download_url(url: str, destination: Path) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        destination.write_bytes(response.content)


async def _download_chart_reference(
    reference: ChartReference, destination_dir: Path
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)

    if reference.kind in {"malody_cid", "malody_sid"}:
        from . import malody_download

        if reference.kind == "malody_cid":
            name = (
                await malody_download.fetch_song_name_from_chart(reference.value)
                or f"chart_{reference.value}"
            )
            cids = [reference.value]
        else:
            cids = await malody_download.fetch_cids_from_sid(reference.value)
            if not cids:
                raise ValueError(f"SID {reference.value} 下没有找到谱面")
            name = (
                await malody_download.fetch_song_name_from_song(reference.value)
                or f"song_{reference.value}"
            )

        destination = destination_dir / f"{malody_download.safe_filename(name)}.mcz"
        await malody_download.build_mcz(cids, destination)
        return destination

    if reference.kind != "url":
        raise ValueError("不支持的谱面来源")

    destination = destination_dir / (Path(reference.name).name or "chart.osu")
    await _download_url(reference.value, destination)
    data = destination.read_bytes()
    if data.startswith(b"PK\x03\x04") and destination.suffix.lower() not in {
        ".osz",
        ".mcz",
    }:
        corrected = destination.with_suffix(".osz")
        destination.replace(corrected)
        return corrected
    if not data.startswith(b"PK\x03\x04") and destination.suffix.lower() in {
        ".osz",
        ".mcz",
    }:
        corrected = destination.with_suffix(
            ".mc" if destination.suffix.lower() == ".mcz" else ".osu"
        )
        destination.replace(corrected)
        return corrected
    return destination


async def _send_result_file(bot: Bot, event: MessageEvent, file_path: Path) -> None:
    if isinstance(event, GroupMessageEvent):
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(file_path),
            name=file_path.name,
        )
        return
    if isinstance(event, PrivateMessageEvent):
        await bot.upload_private_file(
            user_id=event.user_id,
            file=str(file_path),
            name=file_path.name,
        )
        return
    raise ValueError(f"不支持的消息类型: {type(event)}")


speed_matcher = on_command(
    COMMAND_PREFIX,
    priority=5,
    block=True,
    rule=Rule(_onebot_command_rule),
)
pitch_speed_matcher = on_command(
    PITCH_SPEED_COMMAND_PREFIX,
    priority=5,
    block=True,
    rule=Rule(_onebot_command_rule),
)


async def _handle_speed_request(
    bot: Bot,
    event: MessageEvent,
    matcher,
    command_prefix: str,
    audio_processor,
    mode_label: str,
    args_text: str,
):
    try:
        command_text = f"{command_prefix} {args_text}".strip()
        reference_token, rate_tokens = _split_speed_command(command_text, command_prefix)
        rates = _parse_rate_tokens(rate_tokens, command_prefix)
    except ValueError as exc:
        await matcher.finish(str(exc))

    file_info = _extract_file_info(event)
    reference = _parse_chart_reference(reference_token) if reference_token else None
    if reference_token and reference is None:
        await matcher.finish("无法识别谱面来源，请使用 bid、cid、sid 或有效的谱面链接。")
    if file_info and reference is not None:
        await matcher.finish("请在文件附件和谱面链接之间选择一个来源。")
    if not file_info and reference is None:
        await matcher.finish(
            "请发送或回复 .osu、.osz、.mc、.mcz 文件，或提供 bid、cid、sid、谱面链接。"
        )

    if file_info:
        source_name = Path(file_info["name"]).name
        if Path(source_name).suffix.lower() not in CHART_INPUT_SUFFIXES:
            await matcher.finish("只支持 .osu、.osz、.mc、.mcz 文件。")
    else:
        source_name = reference.name

    rate_label = ", ".join(f"x{_format_decimal(rate)}" for rate in rates)
    output_description = (
        f"原速 + {rate_label}" if len(rates) > 1 else rate_label
    )
    logger.info(
        f"[mcz_speed] 开始处理 {source_name}，模式：{mode_label}，倍率：{output_description}"
    )
    await bot.send(
        event,
        f"已收到，正在处理 {source_name}，模式：{mode_label}，倍率：{output_description}。",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        input_path = temp_root / source_name
        try:
            if file_info is not None:
                if not await _download_file(bot, file_info, input_path):
                    await matcher.finish("下载谱面文件失败。")
            else:
                input_path = await _download_chart_reference(reference, temp_root)

            output_path = await _process_chart_input(
                input_path,
                temp_root,
                rates,
                audio_processor,
            )
        except zipfile.BadZipFile:
            await matcher.finish("文件不是有效的谱面压缩包。")
        except Exception as e:
            logger.error(f"[mcz_speed] 处理失败: {e}")
            await matcher.finish("谱面处理失败：请反馈bot主人")

        logger.info(f"[mcz_speed] 处理完成: {output_path}")

        try:
            await _send_result_file(bot, event, output_path)
        except Exception as e:
            logger.error(f"[mcz_speed] 发送文件失败: {e}")
            await matcher.finish("发送文件失败：请反馈bot主人")


@speed_matcher.handle()
async def handle_speed(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
):
    await _handle_speed_request(
        bot,
        event,
        speed_matcher,
        COMMAND_PREFIX,
        _run_ffmpeg_atempo,
        "保持音调",
        args.extract_plain_text(),
    )


@pitch_speed_matcher.handle()
async def handle_speed_pitch(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
):
    await _handle_speed_request(
        bot,
        event,
        pitch_speed_matcher,
        PITCH_SPEED_COMMAND_PREFIX,
        _run_ffmpeg_speed_pitch,
        "变调",
        args.extract_plain_text(),
    )


def _extract_mcz_archive(mcz_path: Path, extract_dir: Path) -> None:
    base_dir = extract_dir.resolve()
    with zipfile.ZipFile(mcz_path, "r") as archive:
        for member in archive.infolist():
            target_path = (extract_dir / member.filename).resolve()
            if not target_path.is_relative_to(base_dir):
                raise ValueError(f"压缩包包含非法路径: {member.filename}")
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
