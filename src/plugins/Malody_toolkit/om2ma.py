"""Convert osu!mania beatmaps and archives to Malody charts and packages."""

import json
import math
import shutil
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
)
from nonebot.log import logger
from nonebot.exception import FinishedException

from .ma2om import (
    _extract_archive_safely,
    _repack_archive,
    _send_result_file,
)
from .tool_runner import mp3_to_ogg

# ---------- 命令注册 ----------
om2ma = on_command(
    "om2ma",
    aliases={"osu2mc", "osu2ma", "om2mc"},
    priority=5,
    block=True,
)

def get_reply_file(event: Event) -> Optional[dict]:
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
    file_url = file_info.get("url", "")
    file_id = file_info.get("file_id", "")
    try:
        if file_url and (file_url.startswith("http://") or file_url.startswith("https://")):
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
                if url and (url.startswith("http://") or url.startswith("https://")):
                    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        return True
                elif local_path and Path(local_path).is_file():
                    shutil.copy(local_path, dest)
                    return True
            except Exception as e:
                logger.warning(f"get_file API 失败: {e}")
        if file_url and Path(file_url).is_file():
            shutil.copy(file_url, dest)
            return True
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
    return False

# ---------- 核心解析 ----------
def parse_osu_mania(text: str) -> dict:
    sections = {
        "General": {}, "Metadata": {}, "Difficulty": {},
        "TimingPoints": [], "Events": [], "HitObjects": []
    }
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            continue
        if current is None:
            continue
        if current in ("General", "Metadata", "Difficulty"):
            if ":" in line:
                k, _, v = line.partition(":")
                sections[current][k.strip()] = v.strip()
        elif current == "TimingPoints":
            parts = line.split(",")
            if len(parts) >= 8:
                sections["TimingPoints"].append(parts)
        elif current == "Events":
            sections["Events"].append(line)
        elif current == "HitObjects":
            sections["HitObjects"].append(line)

    mode = int(sections["General"].get("Mode", "0"))
    if mode != 3:
        raise ValueError("只支持 osu!mania (Mode=3)")

    cs = float(sections["Difficulty"].get("CircleSize", "4"))
    keys = int(cs)

    title = sections["Metadata"].get("Title", "Unknown")
    artist = sections["Metadata"].get("Artist", "Unknown")
    title_org = sections["Metadata"].get("TitleUnicode", title)
    artist_org = sections["Metadata"].get("ArtistUnicode", artist)
    creator = sections["Metadata"].get("Creator", "Unknown")
    version = sections["Metadata"].get("Version", "Normal")
    preview = int(sections["General"].get("PreviewTime", "-1"))
    if preview < 0:
        preview = 0
    audio = sections["General"].get("AudioFilename", "")
    bg = sections["General"].get("Background", "")
    if not bg:
        for evt in sections["Events"]:
            if evt.startswith("0,0,"):
                parts = evt.split(",")
                if len(parts) >= 3:
                    bg = parts[2].strip().strip('"')
                    break

    # 解析所有 Timing Points
    all_tps = []
    for p in sections["TimingPoints"]:
        try:
            off = float(p[0])
            ms = float(p[1])
            meter = int(p[2]) if len(p) > 2 else 4
            volume = int(p[5]) if len(p) > 5 else 100
            inh = int(p[6]) if len(p) > 6 else 1
            all_tps.append({
                "offset": off, "ms_per_beat": ms,
                "meter": meter, "volume": volume, "uninherited": inh == 1
            })
        except ValueError:
            continue
    if not all_tps:
        raise ValueError("无 Timing Points")

    # 确保第一个是红线
    if not all_tps[0]["uninherited"]:
        all_tps.insert(0, {
            "offset": all_tps[0]["offset"],
            "ms_per_beat": 500,
            "meter": 4,
            "volume": 100,
            "uninherited": True
        })

    # 寻找第一个红线作为基准
    base_tp = next(tp for tp in all_tps if tp["uninherited"])
    bpm = 60000.0 / base_tp["ms_per_beat"]   # 高精度

    # 时间转换
    def ms_to_beat(ms: float) -> float:
        return (ms - base_tp["offset"]) / base_tp["ms_per_beat"]

    # time 数组
    time = [{"beat": [0, 0, 1], "bpm": bpm, "delay": 0}]

    # 构建 effect
    effects = [{"beat": [0, 0, 1], "sign": 4}]
    sorted_tps = sorted(all_tps, key=lambda x: x["offset"])
    prev_ggt = False
    for tp in sorted_tps:
        if tp is base_tp:
            continue
        if not tp["uninherited"]:
            beat = max(0, ms_to_beat(tp["offset"]))
            prev_ggt = not prev_ggt
            effects.append({
                "beat": _beat_to_frac(beat),
                "ggt": prev_ggt
            })

    # 音量随时间变化
    volume_events = [(tp["offset"], tp["volume"]) for tp in sorted_tps]
    def get_vol(ms: float) -> int:
        vol = 50
        for off, v in volume_events:
            if off <= ms:
                vol = v
        return vol

    # 解析 HitObjects
    notes = []
    for obj_line in sections["HitObjects"]:
        parts = obj_line.split(",")
        if len(parts) < 5:
            continue
        try:
            x = int(parts[0])
            t = float(parts[2])
            typ = int(parts[3])
            extras = parts[5] if len(parts) > 5 else ""
        except (ValueError, IndexError):
            continue

        col = min(max(int((x * keys) / 512), 0), keys - 1)
        beat = ms_to_beat(t)
        if beat < 0:
            beat = 0

        vol = get_vol(t)
        sound = "soft-hitnormal.wav"
        group = 1

        end_t = 0.0
        custom_sound = None
        custom_vol = None

        if extras:
            segs = extras.split(":")
            # 长条结束时间
            if segs[0]:
                try:
                    end_t = float(segs[0])
                except ValueError:
                    pass
            # 提取音效文件名和音量
            for i, s in enumerate(segs):
                if s and not s.isdigit() and '.' in s:
                    custom_sound = s
                    if i > 0 and segs[i-1].isdigit():
                        custom_vol = int(segs[i-1])
                    break

        if custom_sound:
            sound = custom_sound
            if custom_vol is not None:
                vol = custom_vol

        note_entry = {
            "beat": _beat_to_frac(beat),
            "sound": sound,
            "column": col,
            "vol": vol,
            "group": group
        }
        if (typ & 128) and end_t > 0:
            end_beat = ms_to_beat(end_t)
            if end_beat > beat:
                note_entry["endbeat"] = _beat_to_frac(end_beat)
        notes.append(note_entry)

    # 排序
    def beat_sort_key(n):
        b = n["beat"]
        return b[0] + b[1] / b[2] if b[2] != 0 else b[0]
    notes.sort(key=beat_sort_key)

    # 添加主音源 note (type 1) 至末尾
    if audio:
        notes.append({
            "beat": [0, 0, 1],
            "type": 1,
            "sound": audio,
            "x": 10
        })

    return {
        "creator": creator,
        "background": bg,
        "version": version,
        "preview": preview,
        "title": title,
        "artist": artist,
        "titleorg": title_org,
        "artistorg": artist_org,
        "audio": audio,
        "keys": keys,
        "bpm": bpm,
        "time": time,
        "effects": effects,
        "notes": notes
    }

def _beat_to_frac(val: float, denom: int = 480) -> list:
    val = max(0, val)
    ticks = int(round(val * denom))
    integer = ticks // denom
    num = ticks % denom
    if num == 0:
        return [integer, 0, 1]
    g = math.gcd(num, denom)
    return [integer, num // g, denom // g]

def build_mc_json(data: dict) -> dict:
    meta = {
        "id": 0,
        "creator": data["creator"],
        "background": data["background"],
        "cover": "",
        "version": data["version"],
        "preview": data["preview"],
        "mode": 0,
        "song": {
            "title": data["title"],
            "artist": data["artist"],
            "titleorg": data["titleorg"],
            "artistorg": data["artistorg"],
            "file": data["audio"],
            "bpm": data["bpm"]
        },
        "mode_ext": {
            "column": data["keys"],
            "bar_begin": 0
        },
        "aimode": ""
    }
    mc = {
        "meta": meta,
        "time": data["time"],
        "note": data["notes"]
    }
    if data.get("effects"):
        mc["effect"] = data["effects"]
    mc["extra"] = None
    return mc

def osu_to_mc(osu_content: str) -> str:
    data = parse_osu_mania(osu_content)
    mc_obj = build_mc_json(data)
    return json.dumps(mc_obj, indent=2, ensure_ascii=False)

def _osu_audio_filename(text: str) -> str:
    in_general = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_general = line[1:-1].strip().lower() == "general"
            continue
        if in_general and line.lower().startswith("audiofilename:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def _resolve_archive_audio(
    archive_root: Path,
    chart_path: Path,
    reference: str,
) -> Path:
    normalized = reference.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or (relative.parts and ":" in relative.parts[0])
    ):
        raise ValueError(f"osu 文件包含非法音频路径：{reference}")

    target = chart_path.parent.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(archive_root.resolve()):
        raise ValueError(f"osu 文件音频路径超出压缩包目录：{reference}")
    return target


def _unique_audio_output(source: Path) -> Path:
    candidate = source.with_suffix(".ogg")
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = source.with_name(f"{source.stem}__from_mp3_{index}.ogg")
        if not candidate.exists():
            return candidate
        index += 1


async def _convert_archive_mp3(
    source: Path,
    converted_audio: dict[Path, Path],
    original_mp3s: set[Path],
) -> Path:
    source = source.resolve()
    if source in converted_audio:
        return converted_audio[source]
    if not source.is_file():
        raise ValueError(f"压缩包中找不到 osu 文件引用的音频：{source.name}")

    original_mp3s.add(source)
    with tempfile.TemporaryDirectory(prefix="osu2mc_audio_") as temporary:
        stage = Path(temporary) / source.name
        stage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, stage)
        converted = await mp3_to_ogg(stage)
        output = _unique_audio_output(source)
        shutil.move(str(converted), output)

    converted_audio[source] = output
    return output


async def _convert_mc_audio_references(
    mc_path: Path,
    archive_root: Path,
    chart_path: Path,
    osu_audio: str,
    converted_audio: dict[Path, Path],
    original_mp3s: set[Path],
) -> None:
    data = json.loads(mc_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return False
    references = []
    meta = data.get("meta", {})
    song = meta.get("song", {}) if isinstance(meta, dict) else {}
    if isinstance(song, dict) and song.get("file"):
        references.append((song, "file", str(song["file"])))
    for note in data.get("note", []):
        if isinstance(note, dict) and note.get("sound"):
            references.append((note, "sound", str(note["sound"])))

    if osu_audio and not any(value == osu_audio for _, _, value in references):
        if isinstance(song, dict):
            references.append((song, "file", osu_audio))

    changed = False
    for owner, key, reference in references:
        if Path(reference.replace("\\", "/")).suffix.lower() != ".mp3":
            continue
        source = _resolve_archive_audio(archive_root, chart_path, reference)
        output = await _convert_archive_mp3(source, converted_audio, original_mp3s)
        owner[key] = PurePosixPath(
            reference.replace("\\", "/")
        ).with_name(output.name).as_posix()
        changed = True

    if changed:
        mc_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _malody_chart_references_audio(mc_path: Path, audio_path: Path) -> bool:
    try:
        data = json.loads(mc_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False

    references = []
    meta = data.get("meta", {})
    song = meta.get("song", {}) if isinstance(meta, dict) else {}
    if isinstance(song, dict) and song.get("file"):
        references.append(str(song["file"]))
    notes = data.get("note", [])
    if isinstance(notes, list):
        references.extend(
            str(note["sound"])
            for note in notes
            if isinstance(note, dict) and note.get("sound")
        )
    for reference in references:
        relative = PurePosixPath(reference.replace("\\", "/"))
        if relative.is_absolute() or (relative.parts and ":" in relative.parts[0]):
            continue
        if mc_path.parent.joinpath(*relative.parts).resolve() == audio_path.resolve():
            return True
    return False


async def convert_osu_to_malody(input_path: Path) -> Path:
    """Convert an osu!mania beatmap or .osz/.zip package to Malody .mc/.mcz."""
    suffix = input_path.suffix.lower()
    if suffix == ".osu":
        mc_path = input_path.with_suffix(".mc")
        if mc_path.exists():
            index = 1
            while True:
                mc_path = input_path.with_name(f"{input_path.stem}__from_osu_{index}.mc")
                if not mc_path.exists():
                    break
                index += 1
        mc_path.write_text(
            osu_to_mc(input_path.read_text(encoding="utf-8", errors="ignore")),
            encoding="utf-8",
        )
        return mc_path
    if suffix not in {".osz", ".zip"}:
        raise ValueError("只支持 .osu、.osz 和 .zip 文件")

    work_dir = input_path.parent / f"{input_path.stem}_mc_work"
    _extract_archive_safely(input_path, work_dir)
    osu_files = sorted(
        path for path in work_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".osu"
    )
    if not osu_files:
        raise ValueError("压缩包中没有找到 .osu 谱面")

    converted_audio: dict[Path, Path] = {}
    original_mp3s: set[Path] = set()
    for osu_path in osu_files:
        osu_text = osu_path.read_text(encoding="utf-8", errors="ignore")
        osu_audio = _osu_audio_filename(osu_text)
        mc_text = osu_to_mc(osu_text)

        mc_path = osu_path.with_suffix(".mc")
        if mc_path.exists():
            index = 1
            while True:
                mc_path = osu_path.with_name(f"{osu_path.stem}__from_osu_{index}.mc")
                if not mc_path.exists():
                    break
                index += 1
        mc_path.write_text(mc_text, encoding="utf-8")
        await _convert_mc_audio_references(
            mc_path,
            work_dir,
            osu_path,
            osu_audio,
            converted_audio,
            original_mp3s,
        )
        osu_path.unlink(missing_ok=True)

    for mp3_path in original_mp3s:
        if not any(
            _malody_chart_references_audio(chart_path, mp3_path)
            for chart_path in work_dir.rglob("*.mc")
            if chart_path.is_file()
        ):
            mp3_path.unlink(missing_ok=True)

    output_path = input_path.with_suffix(".mcz")
    if output_path == input_path:
        output_path = input_path.with_name(f"{input_path.stem}_converted.mcz")
    if output_path.exists():
        index = 1
        while True:
            candidate = output_path.with_name(
                f"{output_path.stem}_{index}{output_path.suffix}"
            )
            if not candidate.exists():
                output_path = candidate
                break
            index += 1
    _repack_archive(work_dir, output_path)
    return output_path


@om2ma.handle()
async def handle_om2ma(bot: Bot, event: Event):
    file_info = get_reply_file(event)
    if not file_info:
        await om2ma.finish("请发送或回复 .osu、.osz 或 .zip 文件。")

    file_name = Path(str(file_info["name"])).name
    if Path(file_name).suffix.lower() not in {".osu", ".osz", ".zip"}:
        await om2ma.finish("om2ma 只支持 .osu、.osz 和 .zip 文件。")

    try:
        with tempfile.TemporaryDirectory(prefix="osu2mc_") as temporary:
            source = Path(temporary) / file_name
            if not await download_file(bot, file_info, source):
                await om2ma.finish("下载谱面文件失败，请重试。")
            output = await convert_osu_to_malody(source)
            await _send_result_file(bot, event, output)
    except FinishedException:
        raise
    except (ValueError, FileNotFoundError, RuntimeError, zipfile.BadZipFile) as exc:
        logger.exception(f"[{file_name}] osu!mania 转 Malody 失败")
        await om2ma.finish("转换失败：请检查谱面和音频文件后重试。")
    except Exception as exc:
        logger.exception(f"[{file_name}] osu!mania 转 Malody 出错")
        await om2ma.finish("转换出错，请检查后台日志。")
