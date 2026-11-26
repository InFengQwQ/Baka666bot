"""Run the bundled conversion tools, using wine on Linux."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import tempfile
from pathlib import Path

from nonebot.log import logger

from src.plugin_runtime import require_executable, tool_path

# Tools that only exist as Windows executables.
WINE_TOOLS = frozenset({"ma2om.exe", "ncm2mp3.exe", "prontom.exe"})
WINDOWS_BAD_CHARS = frozenset('<>:"/\\|?*')

CONVERSION_EXTS = {
    "ma2om": (".mc", ".mcz", ".osz", ".zip"),
    "mp32ogg": (".mp3",),
    "ncm2mp3": (".ncm",),
    "ncm2ogg": (".ncm",),
}

TOOL_TIMEOUT = 300

_wine_slots: asyncio.Semaphore | None = None
_prefix_lock = asyncio.Lock()


def decode_output(value: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            decoded = value.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if decoded:
            return decoded
    return value.decode("utf-8", "replace").strip()


def is_binary_tool(path: Path) -> bool:
    return path.suffix.lower() == ".exe"


def _uses_wine(executable: Path) -> bool:
    return os.name != "nt" and executable.name.lower() in WINE_TOOLS


def _wine_binary() -> str:
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        raise RuntimeError("当前系统没有 wine，无法运行该转换工具")
    return wine


def _wine_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WINEPREFIX", str(Path.home() / ".wine"))
    env["WINEDEBUG"] = "-all"
    env["WINEDLLOVERRIDES"] = "mscoree,mshtml="
    env.pop("DISPLAY", None)
    return env


def _wine_path(path: Path) -> str:
    return "Z:" + str(path.resolve()).replace("/", "\\")


def _needs_staging(path: Path) -> bool:
    text = str(path)
    return not text.isascii() or any(c in WINDOWS_BAD_CHARS for c in path.name)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _wine_semaphore() -> asyncio.Semaphore:
    global _wine_slots
    if _wine_slots is None:
        limit = int(os.environ.get("BAKA_WINE_CONCURRENCY", "2"))
        _wine_slots = asyncio.Semaphore(max(1, limit))
    return _wine_slots


def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _prefix_ready(env: dict[str, str]) -> bool:
    prefix = Path(env["WINEPREFIX"])
    return (prefix / "drive_c/windows/system32/kernel32.dll").is_file()


async def _ensure_prefix() -> None:
    env = _wine_env()
    if _prefix_ready(env):
        return
    async with _prefix_lock:
        if _prefix_ready(env):
            return
        logger.info(f"[tool-runner] 初始化 wine prefix: {env['WINEPREFIX']}")
        process = await asyncio.create_subprocess_exec(
            _wine_binary(),
            "wineboot",
            "-u",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            _kill(process)
            raise RuntimeError("wine prefix 初始化超时")


async def _spawn(
    command: list[str],
    env: dict[str, str] | None,
    cwd: Path,
    label: str,
) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=TOOL_TIMEOUT
        )
    except asyncio.TimeoutError:
        _kill(process)
        raise RuntimeError(f"{label} 执行超时")
    return process.returncode, stdout, stderr


async def run_native_tool(
    executable_path: Path,
    input_path: Path,
    extra_args: tuple[str, ...] = (),
    output_suffix: str | tuple[str, ...] = ".mc",
) -> Path:
    if not executable_path.is_file():
        raise FileNotFoundError(f"找不到工具程序：{executable_path}")

    suffixes = (
        (output_suffix,) if isinstance(output_suffix, str) else tuple(output_suffix)
    )
    suffixes = tuple(suffix.lower() for suffix in suffixes)

    use_wine = _uses_wine(executable_path)
    work_dir = input_path.parent
    target = input_path
    stage_dir: Path | None = None
    if use_wine:
        await _ensure_prefix()
        if _needs_staging(input_path):
            stage_dir = Path(tempfile.mkdtemp(prefix="tool_"))
            target = stage_dir / f"input{input_path.suffix}"
            shutil.copy2(input_path, target)
            work_dir = stage_dir

    if use_wine:
        command = [
            _wine_binary(),
            str(executable_path),
            _wine_path(target),
            *extra_args,
        ]
        env = _wine_env()
    else:
        command = [str(executable_path), str(target), *extra_args]
        env = None

    logger.info(
        "[chart-tool] executing: "
        + " ".join(f'"{value}"' if " " in value else value for value in command)
    )
    before = {path for path in work_dir.iterdir() if path.is_file()}
    try:
        if use_wine:
            async with _wine_semaphore():
                returncode, stdout, stderr = await _spawn(
                    command, env, work_dir, executable_path.name
                )
        else:
            returncode, stdout, stderr = await _spawn(
                command, env, work_dir, executable_path.name
            )

        generated = sorted(
            path
            for path in work_dir.iterdir()
            if path.is_file()
            and path not in before
            and path.suffix.lower() in suffixes
        )
        logger.info(
            f"[chart-tool] exit={returncode} "
            f"input={input_path.name} args={list(extra_args)}"
        )
        if returncode != 0 or not generated:
            detail = decode_output(stderr) or decode_output(stdout)
            if detail:
                raise RuntimeError(detail)
            if returncode != 0:
                raise RuntimeError(
                    f"{executable_path.name} 退出码 {returncode}，未生成输出文件"
                )
            raise RuntimeError(f"{executable_path.name} 未生成输出文件")

        output = generated[0]
        if stage_dir is not None:
            target_name = _unique_path(input_path.with_suffix(output.suffix))
            # shutil.move handles /tmp and the data volume being different filesystems.
            output = Path(shutil.move(str(output), str(target_name)))
    finally:
        if stage_dir is not None:
            shutil.rmtree(stage_dir, ignore_errors=True)

    logger.info(
        f"[chart-tool] generated={output.name} "
        f"stdout={decode_output(stdout)}"
    )
    return output


async def mp3_to_ogg(source: Path) -> Path:
    ffmpeg = require_executable("ffmpeg", "请安装 FFmpeg 并加入 PATH")
    output = _unique_path(source.with_suffix(".ogg"))
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-c:a",
        "libvorbis",
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0 or not output.is_file():
        raise RuntimeError(decode_output(stderr) or "ffmpeg 未生成 ogg 文件")
    return output


async def ncm_to_audio(source: Path) -> Path:
    # 网易云缓存里可能是 mp3 也可能是 flac。
    return await run_native_tool(
        tool_path("ncm2mp3.exe"), source, output_suffix=(".mp3", ".flac")
    )


async def ncm_to_ogg(source: Path) -> Path:
    audio = await ncm_to_audio(source)
    try:
        return await mp3_to_ogg(audio)
    finally:
        audio.unlink(missing_ok=True)


async def run_conversion(tool_key: str, input_path: Path) -> list[Path]:
    if tool_key == "mp32ogg":
        return [await mp3_to_ogg(input_path)]
    if tool_key == "ncm2mp3":
        return [await ncm_to_audio(input_path)]
    if tool_key == "ncm2ogg":
        return [await ncm_to_ogg(input_path)]
    raise ValueError(f"未知转换工具：{tool_key}")
