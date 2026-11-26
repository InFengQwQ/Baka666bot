from __future__ import annotations

import asyncio
import json
import math
import shutil
import tempfile
import zipfile
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg

from .ma2om import _extract_archive_safely, _repack_archive
from .mcz_speed import _download_file, _extract_file_info, _send_result_file


timeinverse = on_command("timeinverse", priority=5, block=True)
CHART_SUFFIXES = {".osu", ".mc", ".osz", ".mcz"}
MAX_BEAT_DENOMINATOR = 1_000_000


@dataclass(frozen=True)
class _BeatPoint:
    beat: Fraction
    bpm: float
    data: dict[str, Any]


def _beat_value(value: Any) -> Fraction:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"无效的 Malody beat 值: {value!r}")
    bar, numerator, denominator = (int(part) for part in value)
    if denominator <= 0:
        raise ValueError(f"无效的 Malody beat 分母: {denominator}")
    return Fraction(bar * denominator + numerator, denominator)


def _beat_array(value: float | Fraction) -> list[int]:
    fraction = Fraction(value).limit_denominator(MAX_BEAT_DENOMINATOR)
    whole, remainder = divmod(fraction.numerator, fraction.denominator)
    return [whole, remainder, fraction.denominator] if remainder else [whole, 0, 1]


def _number(value: Any, default: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        if default is None:
            raise ValueError(f"无效的数值: {value!r}")
        return default
    if not math.isfinite(result):
        raise ValueError(f"无效的数值: {value!r}")
    return result


def _prepare_mc_tempo(items: Any) -> tuple[list[_BeatPoint], list[_BeatPoint], float]:
    if not isinstance(items, list) or not items:
        raise ValueError(".mc 缺少有效的 time BPM 列表")
    actual: list[_BeatPoint] = []
    for item in items:
        if not isinstance(item, dict) or "beat" not in item or "bpm" not in item:
            continue
        beat = _beat_value(item["beat"])
        bpm = _number(item["bpm"])
        if bpm <= 0:
            raise ValueError("BPM 必须大于 0")
        delay = _number(item.get("delay", 0), 0)
        if delay and beat != 0:
            raise ValueError("暂不支持非零拍点上的 time.delay，避免反转后产生错位")
        actual.append(_BeatPoint(beat, bpm, dict(item)))
    if not actual:
        raise ValueError(".mc 的 time 列表中没有可用 BPM")
    actual.sort(key=lambda point: point.beat)
    deduplicated: list[_BeatPoint] = []
    for point in actual:
        if deduplicated and deduplicated[-1].beat == point.beat:
            deduplicated[-1] = point
        else:
            deduplicated.append(point)
    actual = deduplicated
    zero_index = next((i for i, point in enumerate(actual) if point.beat == 0), None)
    if zero_index is None:
        prior = [point for point in actual if point.beat < 0]
        baseline = prior[-1] if prior else actual[0]
        working = sorted(
            [*actual, _BeatPoint(Fraction(0), baseline.bpm, {"beat": [0, 0, 1], "bpm": baseline.bpm})],
            key=lambda point: point.beat,
        )
        start_delay = 0.0
    else:
        working = actual[:]
        start_delay = _number(actual[zero_index].data.get("delay", 0), 0)
    return actual, working, start_delay


def _integrate_beats(start: Fraction, end: Fraction, points: list[_BeatPoint]) -> float:
    if end <= start:
        return 0.0
    boundaries = [start]
    boundaries.extend(point.beat for point in points if start < point.beat < end)
    boundaries.append(end)
    positions = [point.beat for point in points]
    elapsed = 0.0
    for left, right in zip(boundaries, boundaries[1:]):
        middle = (left + right) / 2
        index = bisect_right(positions, middle) - 1
        elapsed += float(right - left) * 60_000 / points[max(index, 0)].bpm
    return elapsed


def _mc_beat_to_ms(beat: Fraction, points: list[_BeatPoint], start_delay: float) -> float:
    if beat >= 0:
        return start_delay + _integrate_beats(Fraction(0), beat, points)
    return start_delay - _integrate_beats(beat, Fraction(0), points)


def _integrate_time(start: float, end: float, points: list[tuple[float, float]]) -> float:
    if end <= start:
        return 0.0
    boundaries = [start]
    boundaries.extend(time for time, _ in points if start < time < end)
    boundaries.append(end)
    positions = [time for time, _ in points]
    elapsed = 0.0
    for left, right in zip(boundaries, boundaries[1:]):
        middle = (left + right) / 2
        index = bisect_right(positions, middle) - 1
        elapsed += (right - left) * points[max(index, 0)][1] / 60_000
    return elapsed


def _mc_ms_to_beat(time_ms: float, points: list[tuple[float, float]]) -> Fraction:
    elapsed = _integrate_time(0, time_ms, points) if time_ms >= 0 else -_integrate_time(time_ms, 0, points)
    return Fraction(elapsed).limit_denominator(MAX_BEAT_DENOMINATOR)


def _reverse_mc_tempo(
    items: Any, mirror_ms: float
) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
    actual, working, start_delay = _prepare_mc_tempo(items)
    old_times = [_mc_beat_to_ms(point.beat, working, start_delay) for point in actual]
    anchor_index = max(0, bisect_left(old_times, mirror_ms) - 1)
    records: dict[float, tuple[dict[str, Any], float]] = {}

    def add_record(time_ms: float, source: _BeatPoint, bpm: float) -> None:
        record = dict(source.data)
        record["bpm"] = bpm
        if "delay" in record:
            record["delay"] = 0
        records[round(time_ms, 7)] = (record, bpm)

    anchor = actual[anchor_index]
    add_record(0, anchor, anchor.bpm)
    for index in range(1, len(actual)):
        previous = actual[index - 1]
        add_record(mirror_ms - old_times[index], previous, previous.bpm)

    reversed_points = sorted(
        ((time_ms, bpm) for time_ms, (_, bpm) in records.items()), key=lambda point: point[0]
    )
    converted: list[dict[str, Any]] = []
    for time_ms, (record, _) in records.items():
        record["beat"] = _beat_array(_mc_ms_to_beat(time_ms, reversed_points))
        converted.append(record)
    converted.sort(key=lambda item: _beat_value(item["beat"]))
    return converted, reversed_points


def _reverse_mc_objects(
    items: Any,
    old_points: list[_BeatPoint],
    start_delay: float,
    new_points: list[tuple[float, float]],
    mirror_ms: float,
    *,
    ignored_indices: set[int] | None = None,
) -> None:
    if not isinstance(items, list):
        return
    ignored_indices = ignored_indices or set()
    for index, item in enumerate(items):
        if index in ignored_indices or not isinstance(item, dict) or "beat" not in item:
            continue
        start_beat = _beat_value(item["beat"])
        start_ms = _mc_beat_to_ms(start_beat, old_points, start_delay)
        if "endbeat" in item:
            end_ms = _mc_beat_to_ms(_beat_value(item["endbeat"]), old_points, start_delay)
            if end_ms < start_ms:
                raise ValueError(".mc 长条 endbeat 早于 beat")
            item["beat"] = _beat_array(_mc_ms_to_beat(mirror_ms - end_ms, new_points))
            item["endbeat"] = _beat_array(_mc_ms_to_beat(mirror_ms - start_ms, new_points))
        else:
            item["beat"] = _beat_array(_mc_ms_to_beat(mirror_ms - start_ms, new_points))


def _mc_audio_note(data: dict[str, Any]) -> tuple[int, str, float]:
    notes = data.get("note")
    if not isinstance(notes, list):
        raise ValueError(".mc 缺少 note 数组")
    candidates = []
    for index, note in enumerate(notes):
        if not isinstance(note, dict) or not isinstance(note.get("sound"), str):
            continue
        try:
            note_type = int(note.get("type", 0))
        except (TypeError, ValueError):
            continue
        if note_type == 1:
            candidates.append((index, note))
    if not candidates:
        raise ValueError(".mc 中找不到 type=1 的音频标记")
    sounds = {note["sound"] for _, note in candidates}
    if len(sounds) != 1:
        raise ValueError("暂不支持一张 .mc 包含多个主音频")
    index, note = candidates[0]
    return index, note["sound"], _number(note.get("offset", 0), 0)


def _reverse_mc_chart(data: dict[str, Any], duration_ms: float, audio_name: str) -> None:
    _, old_audio_name, audio_offset = _mc_audio_note(data)
    mirror_ms = duration_ms - 2 * audio_offset
    _, old_points, start_delay = _prepare_mc_tempo(data.get("time"))
    reversed_time, new_points = _reverse_mc_tempo(data.get("time"), mirror_ms)
    notes = data["note"]
    audio_indices: set[int] = set()
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            continue
        try:
            is_audio = int(note.get("type", 0) or 0) == 1
        except (TypeError, ValueError):
            is_audio = False
        if is_audio and note.get("sound") == old_audio_name:
            note["sound"] = audio_name
            audio_indices.add(index)
    _reverse_mc_objects(
        notes, old_points, start_delay, new_points, mirror_ms, ignored_indices=audio_indices
    )
    playable = [note for i, note in enumerate(notes) if i not in audio_indices]
    markers = [note for i, note in enumerate(notes) if i in audio_indices]
    playable.sort(
        key=lambda note: _beat_value(note["beat"])
        if isinstance(note, dict) and "beat" in note
        else Fraction(0)
    )
    data["note"] = playable + markers
    data["time"] = reversed_time

    bpmlist = data.get("bpmlist")
    if isinstance(bpmlist, list) and bpmlist:
        if all(isinstance(item, (int, float)) for item in bpmlist):
            data["bpmlist"] = list(reversed(bpmlist))
        elif all(isinstance(item, dict) and "beat" in item and "bpm" in item for item in bpmlist):
            data["bpmlist"], _ = _reverse_mc_tempo(bpmlist, mirror_ms)
        else:
            _reverse_mc_objects(bpmlist, old_points, start_delay, new_points, mirror_ms)
            if all(isinstance(item, dict) and "beat" in item for item in bpmlist):
                bpmlist.sort(key=lambda item: _beat_value(item["beat"]))
            else:
                bpmlist.reverse()
    effects = data.get("effect")
    _reverse_mc_objects(effects, old_points, start_delay, new_points, mirror_ms)
    if isinstance(effects, list):
        effects.sort(
            key=lambda item: _beat_value(item["beat"])
            if isinstance(item, dict) and "beat" in item
            else Fraction(0)
        )

    meta = data.get("meta")
    if isinstance(meta, dict):
        preview = meta.get("preview")
        if preview is not None:
            preview_ms = _number(preview, -1)
            if preview_ms >= 0:
                meta["preview"] = max(0, int(round(duration_ms - preview_ms)))
        song = meta.get("song")
        if isinstance(song, dict):
            if isinstance(song.get("file"), str) and song["file"]:
                song["file"] = audio_name
            if "bpm" in song:
                active = max((point for point in new_points if point[0] <= 0), default=new_points[0], key=lambda point: point[0])
                song["bpm"] = active[1]


def _osu_audio_fields(text: str) -> tuple[str, float, int, int]:
    section = ""
    audio_name = ""
    audio_lead_in = 0.0
    preview_time = -1
    mode = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "General" and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().casefold()
            if key == "audiofilename":
                audio_name = value.strip().strip('"')
            elif key == "audioleadin":
                audio_lead_in = _number(value.strip(), 0)
            elif key == "previewtime":
                preview_time = int(_number(value.strip(), -1))
            elif key == "mode":
                mode = int(_number(value.strip(), 0))
    return audio_name, audio_lead_in, preview_time, mode


def _osu_timing_rows(lines: list[str], mirror_ms: float) -> list[str]:
    redlines: list[tuple[float, list[str]]] = []
    greenlines: list[tuple[float, list[str]]] = []
    other: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            other.append(line)
            continue
        parts = line.split(",")
        if len(parts) < 7:
            other.append(line)
            continue
        try:
            timestamp = float(parts[0])
            inherited = int(parts[6]) == 0
        except ValueError:
            other.append(line)
            continue
        (greenlines if inherited else redlines).append((timestamp, parts))
    if not redlines:
        raise ValueError(".osu 中找不到红线 BPM")

    def collapse(rows: list[tuple[float, list[str]]]) -> list[tuple[float, list[str]]]:
        rows.sort(key=lambda row: row[0])
        result: list[tuple[float, list[str]]] = []
        for row in rows:
            if result and result[-1][0] == row[0]:
                result[-1] = row
            else:
                result.append(row)
        return result

    redlines = collapse(redlines)
    greenlines = collapse(greenlines)
    output: dict[tuple[float, bool], list[str]] = {}

    def add_row(timestamp: float, source: list[str], inherited: bool) -> None:
        row = source[:]
        row[0] = _format_ms(timestamp)
        output[(round(timestamp, 6), inherited)] = row

    red_times = [row[0] for row in redlines]
    active_red = max(0, bisect_left(red_times, mirror_ms) - 1)
    add_row(0, redlines[active_red][1], False)
    for index in range(1, len(redlines)):
        add_row(mirror_ms - redlines[index][0], redlines[index - 1][1], False)

    if greenlines:
        green_times = [row[0] for row in greenlines]
        active_green = bisect_left(green_times, mirror_ms) - 1
        if active_green >= 0:
            add_row(0, greenlines[active_green][1], True)
        default_green = ["0", "-100", "4", "0", "0", "100", "0", "0"]
        for index, (timestamp, _) in enumerate(greenlines):
            prior = greenlines[index - 1][1] if index else default_green
            add_row(mirror_ms - timestamp, prior, True)
    rows = sorted(output.items(), key=lambda item: (item[0][0], item[0][1]))
    return [",".join(row) for _, row in rows] + other


def _format_ms(value: float) -> str:
    return str(int(round(value)))


def _osu_hitobject_rows(lines: list[str], mirror_ms: float) -> list[str]:
    objects: list[tuple[float, int, str]] = []
    other: list[str] = []
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("//"):
            other.append(line)
            continue
        parts = line.split(",")
        if len(parts) < 5:
            raise ValueError(".osu HitObjects 中包含无法解析的对象")
        try:
            start = float(parts[2])
            object_type = int(parts[3])
        except ValueError as exc:
            raise ValueError(".osu HitObjects 中包含无法解析的时间") from exc
        if object_type & 2:
            raise ValueError("仅支持 osu!mania 谱面；该谱面含有滑条")
        end = start
        if object_type & 128:
            if len(parts) < 6 or not parts[5].split(":", 1)[0].strip():
                raise ValueError(".osu 长条缺少结束时间")
            end = float(parts[5].split(":", 1)[0])
        elif object_type & 8:
            if len(parts) < 6:
                raise ValueError(".osu 转盘缺少结束时间")
            end = float(parts[5])
        if end < start:
            raise ValueError(".osu 长对象结束时间早于开始时间")
        parts[2] = _format_ms(mirror_ms - end)
        if object_type & 128:
            extras = parts[5].split(":")
            extras[0] = _format_ms(mirror_ms - start)
            parts[5] = ":".join(extras)
        elif object_type & 8:
            parts[5] = _format_ms(mirror_ms - start)
        objects.append((float(parts[2]), index, ",".join(parts)))
    objects.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in objects] + other


def _reverse_osu_text(
    text: str, duration_ms: float, audio_lead_in: float, new_audio_name: str
) -> str:
    mirror_ms = duration_ms - 2 * audio_lead_in
    output: list[str] = []
    section = ""
    buffer: list[str] = []

    def flush() -> None:
        if section == "TimingPoints":
            output.extend(_osu_timing_rows(buffer, mirror_ms))
        elif section == "HitObjects":
            output.extend(_osu_hitobject_rows(buffer, mirror_ms))
        else:
            for raw_line in buffer:
                line = raw_line
                stripped = raw_line.strip()
                if section == "General" and ":" in raw_line:
                    key, separator, value = raw_line.partition(":")
                    key_name = key.strip().casefold()
                    if key_name == "audiofilename":
                        line = f"{key}{separator} {new_audio_name}"
                    elif key_name == "previewtime":
                        preview = _number(value.strip(), -1)
                        if preview >= 0:
                            line = f"{key}{separator} {max(0, round(duration_ms - preview))}"
                elif section == "Editor" and stripped.casefold().startswith("bookmarks:"):
                    key, _, value = raw_line.partition(":")
                    bookmarks = [mirror_ms - _number(item.strip()) for item in value.split(",") if item.strip()]
                    line = f"{key}: {','.join(_format_ms(item) for item in sorted(bookmarks))}"
                elif section == "Events" and stripped and not stripped.startswith("//"):
                    parts = raw_line.split(",")
                    event_name = parts[0].strip().casefold() if parts else ""
                    if event_name in {"2", "break period"} and len(parts) >= 3:
                        start, end = _number(parts[1]), _number(parts[2])
                        parts[1], parts[2] = _format_ms(mirror_ms - end), _format_ms(mirror_ms - start)
                        line = ",".join(parts)
                    elif event_name == "video" and len(parts) >= 2:
                        parts[1] = _format_ms(mirror_ms - _number(parts[1]))
                        line = ",".join(parts)
                output.append(line)

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            flush()
            buffer = []
            section = stripped[1:-1]
            output.append(raw_line)
        else:
            buffer.append(raw_line)
    flush()
    result = "\n".join(output)
    return result + ("\n" if text.endswith(("\n", "\r")) else "")


def _safe_chart_reference(chart_path: Path, reference: str, root: Path) -> Path:
    relative = PurePosixPath(reference.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"谱面包含越界音频路径: {reference}")
    resolved_root = root.resolve()
    result = (chart_path.parent / Path(*relative.parts)).resolve()
    if not result.is_relative_to(resolved_root):
        raise ValueError(f"谱面包含越界音频路径: {reference}")
    if not result.is_file():
        raise FileNotFoundError(f"找不到谱面引用的音频: {reference}；请发送 .osz/.mcz")
    return result


def _suffixed_path(source: Path, reserved: set[Path]) -> Path:
    index = 1
    while True:
        label = "_timeinverse" if index == 1 else f"_timeinverse_{index}"
        candidate = source.with_name(f"{source.stem}{label}{source.suffix}")
        if not candidate.exists() and candidate not in reserved:
            reserved.add(candidate)
            return candidate
        index += 1


async def _probe_duration_ms(audio_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("未找到 ffprobe，请安装 FFmpeg 并加入 PATH")
    process = await asyncio.create_subprocess_exec(
        ffprobe, "-v", "error", "-show_entries", "format=duration:stream=duration",
        "-of", "json", str(audio_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip() or "读取音频时长失败")
    metadata = json.loads(stdout.decode("utf-8"))
    duration = (metadata.get("format") or {}).get("duration")
    if duration in (None, "N/A"):
        duration = next(
            (stream.get("duration") for stream in metadata.get("streams", []) if stream.get("duration") not in (None, "N/A")),
            None,
        )
    duration_ms = _number(duration)
    if duration_ms <= 0:
        raise ValueError(f"无法读取有效的音频时长: {audio_path.name}")
    return duration_ms * 1000


async def _reverse_audio(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请安装并加入 PATH")
    temporary = destination.with_name(f".{destination.stem}.reversing{destination.suffix}")
    temporary.unlink(missing_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:a:0", "-vn", "-af", "areverse", "-map_metadata", "0",
    ]
    if source.suffix.lower() == ".ogg":
        command.extend(["-c:a", "libvorbis", "-q:a", "6"])
    elif source.suffix.lower() == ".mp3":
        command.extend(["-c:a", "libmp3lame", "-q:a", "0"])
    command.append(str(temporary))
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()
    if process.returncode or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip() or f"反转音频失败: {source.name}")
    temporary.replace(destination)


async def _process_mc_workspace(work_dir: Path) -> None:
    charts = sorted(path for path in work_dir.rglob("*.mc") if path.is_file())
    if not charts:
        raise ValueError(".mcz 中没有找到 .mc 谱面")
    reserved: set[Path] = set()
    audio_jobs: dict[Path, Path] = {}
    chart_jobs: list[tuple[Path, Path, dict[str, Any], Path, str]] = []
    for chart_path in charts:
        try:
            data = json.loads(chart_path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法解析 .mc 谱面: {chart_path.name}") from exc
        if not isinstance(data, dict):
            raise ValueError(f".mc 谱面不是 JSON 对象: {chart_path.name}")
        _, reference, _ = _mc_audio_note(data)
        audio_path = _safe_chart_reference(chart_path, reference, work_dir)
        if audio_path not in audio_jobs:
            audio_jobs[audio_path] = _suffixed_path(audio_path, reserved)
        audio_output = audio_jobs[audio_path]
        audio_relative = audio_output.resolve().relative_to(chart_path.parent.resolve()).as_posix()
        chart_jobs.append((chart_path, _suffixed_path(chart_path, reserved), data, audio_path, audio_relative))

    durations = {path: await _probe_duration_ms(path) for path in audio_jobs}
    for audio_path, audio_output in audio_jobs.items():
        await _reverse_audio(audio_path, audio_output)
    for source_path, output_path, data, audio_path, audio_relative in chart_jobs:
        _reverse_mc_chart(data, durations[audio_path], audio_relative)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        source_path.unlink(missing_ok=True)
    for audio_path in audio_jobs:
        audio_path.unlink(missing_ok=True)


async def _process_osu_workspace(work_dir: Path) -> None:
    charts = sorted(path for path in work_dir.rglob("*.osu") if path.is_file())
    if not charts:
        raise ValueError(".osz 中没有找到 .osu 谱面")
    reserved: set[Path] = set()
    audio_jobs: dict[Path, Path] = {}
    chart_jobs: list[tuple[Path, Path, str, Path, str, float]] = []
    for chart_path in charts:
        text = chart_path.read_text(encoding="utf-8-sig", errors="replace")
        audio_name, lead_in, _, mode = _osu_audio_fields(text)
        if mode != 3:
            raise ValueError(f"仅支持 osu!mania 谱面（Mode=3）: {chart_path.name}")
        if not audio_name:
            raise ValueError(f".osu 缺少 AudioFilename: {chart_path.name}")
        audio_path = _safe_chart_reference(chart_path, audio_name, work_dir)
        if audio_path not in audio_jobs:
            audio_jobs[audio_path] = _suffixed_path(audio_path, reserved)
        audio_output = audio_jobs[audio_path]
        new_audio_name = audio_output.resolve().relative_to(chart_path.parent.resolve()).as_posix()
        chart_jobs.append((chart_path, _suffixed_path(chart_path, reserved), text, audio_path, new_audio_name, lead_in))

    durations = {path: await _probe_duration_ms(path) for path in audio_jobs}
    for audio_path, audio_output in audio_jobs.items():
        await _reverse_audio(audio_path, audio_output)
    for source, output, text, audio_path, audio_name, lead_in in chart_jobs:
        output.write_text(
            _reverse_osu_text(text, durations[audio_path], lead_in, audio_name), encoding="utf-8"
        )
        source.unlink(missing_ok=True)
    for audio_path in audio_jobs:
        audio_path.unlink(missing_ok=True)


def _local_source_path(file_info: dict[str, Any]) -> Path | None:
    source = str(file_info.get("url") or "").strip()
    if source.startswith("file://"):
        source = unquote(urlparse(source).path)
        if len(source) >= 3 and source[0] == "/" and source[2] == ":":
            source = source[1:]
    try:
        path = Path(source)
        return path if path.is_file() else None
    except (OSError, ValueError):
        return None


def _stage_local_audio(source_chart: Path | None, staged_chart: Path, work_dir: Path) -> None:
    if source_chart is None:
        return
    if staged_chart.suffix.lower() == ".osu":
        reference = _osu_audio_fields(staged_chart.read_text(encoding="utf-8-sig", errors="replace"))[0]
    elif staged_chart.suffix.lower() == ".mc":
        data = json.loads(staged_chart.read_text(encoding="utf-8-sig"))
        _, reference, _ = _mc_audio_note(data)
    else:
        return
    relative = PurePosixPath(reference.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        return
    source_root = source_chart.parent.resolve()
    candidate = (source_root / Path(*relative.parts)).resolve()
    if not candidate.is_relative_to(source_root) or not candidate.is_file():
        return
    destination = work_dir / Path(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(candidate, destination)


async def _process_input(input_path: Path, temp_root: Path, file_info: dict[str, Any]) -> Path:
    suffix = input_path.suffix.lower()
    if suffix not in CHART_SUFFIXES:
        raise ValueError("只支持 .osu、.osz、.mc、.mcz 文件")
    work_dir = temp_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    if suffix in {".osz", ".mcz"}:
        await asyncio.to_thread(_extract_archive_safely, input_path, work_dir)
    else:
        staged = work_dir / input_path.name
        shutil.copyfile(input_path, staged)
        _stage_local_audio(_local_source_path(file_info), staged, work_dir)
    if suffix in {".mc", ".mcz"}:
        await _process_mc_workspace(work_dir)
        output_suffix = ".mcz"
    else:
        await _process_osu_workspace(work_dir)
        output_suffix = ".osz"
    output_path = temp_root / f"{input_path.stem}_timeinverse{output_suffix}"
    await asyncio.to_thread(_repack_archive, work_dir, output_path)
    return output_path


@timeinverse.handle()
async def handle_timeinverse(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
) -> None:
    if args.extract_plain_text().strip():
        await timeinverse.finish("用法：发送或回复 .osu/.osz/.mc/.mcz 文件后发送 /timeinverse。")
    file_info = _extract_file_info(event)
    if not file_info:
        await timeinverse.finish("请发送或回复包含音频的 .osz/.mcz，或带有同目录音频的 .osu/.mc 文件。")
    source_name = Path(file_info["name"]).name
    if Path(source_name).suffix.lower() not in CHART_SUFFIXES:
        await timeinverse.finish("只支持 .osu、.osz、.mc、.mcz 文件。")
    await bot.send(event, f"已收到 {source_name}，正在反转音频和谱面时间轴。")

    with tempfile.TemporaryDirectory(prefix="timeinverse_") as temporary:
        temp_root = Path(temporary)
        input_path = temp_root / source_name
        try:
            if not await _download_file(bot, file_info, input_path):
                raise RuntimeError("谱面文件下载失败")
            output_path = await _process_input(input_path, temp_root, file_info)
        except zipfile.BadZipFile:
            await timeinverse.finish("文件不是有效的谱面压缩包。")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            await timeinverse.finish(f"时间反转失败：{exc}")
        except Exception as exc:
            logger.exception(f"[timeinverse] 处理 {source_name} 失败: {exc}")
            await timeinverse.finish("时间反转失败，请反馈给 bot 管理员。")
        try:
            await _send_result_file(bot, event, output_path)
        except Exception as exc:
            logger.exception(f"[timeinverse] 发送 {output_path.name} 失败: {exc}")
            await timeinverse.finish("结果文件发送失败，请反馈给 bot 管理员。")
