"""
/replayrd - 回放渲染指令
回复 .mr / .mrv / .osr 文件并发送 /replayrd 来渲染回放视频
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional

import httpx
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.log import logger
from nonebot.rule import Rule

from .mrv2mr import convert_mrv_to_mr
from src.plugin_runtime import tool_path

# ==================== 配置 ====================
# ManiaReplayMaster Java 工具根目录
MRM_DIR = Path(__file__).parent / "ManiaReplayMaster.zip"
JAVA_EXE = tool_path("java") / "bin" / "java.exe"

# 等待用户发送文件的超时时间（秒）
WAIT_FILE_TIMEOUT = 30

# ==================== 全局状态：等待文件上传 ====================
# key: (group_id, user_id) -> asyncio.Event + result dict
_wait_states: Dict[tuple, dict] = {}


def _match_wait_state(event: MessageEvent) -> bool:
    """检查是否有匹配的等待状态"""
    if not isinstance(event, GroupMessageEvent):
        return False
    key = (event.group_id, event.user_id)
    state = _wait_states.get(key)
    if not state:
        return False

    text = event.get_plaintext().strip()
    if text == "1":
        return True

    valid_exts = state["valid_exts"]
    for seg in event.message:
        if seg.type == "file":
            name = (
                seg.data.get("name")
                or seg.data.get("filename")
                or seg.data.get("file", "")
            )
            if any(name.lower().endswith(ext) for ext in valid_exts):
                return True
    return False


# 全局消息监听：用于接收文件
_file_waiter = on_message(rule=Rule(_match_wait_state), priority=5, block=False)


@_file_waiter.handle()
async def handle_file_waiter(event: GroupMessageEvent):
    key = (event.group_id, event.user_id)
    state = _wait_states.get(key)
    if not state:
        return

    text = event.get_plaintext().strip()
    if text == "1":
        state["event"].set()
        state["result"] = {"__cancel__": True}
        return

    valid_exts = state["valid_exts"]
    for seg in event.message:
        if seg.type == "file":
            name = (
                seg.data.get("name")
                or seg.data.get("filename")
                or seg.data.get("file", "")
            )
            if any(name.lower().endswith(ext) for ext in valid_exts):
                state["event"].set()
                state["result"] = {
                    "name": name,
                    "file_id": seg.data.get("file_id"),
                    "url": seg.data.get("url", ""),
                }
                return


# ==================== 工具函数 ====================

def get_file_info_from_reply(event: MessageEvent) -> Optional[dict]:
    """从回复消息中提取文件信息"""
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
    """下载文件到目标路径，返回是否成功"""
    file_url = file_info.get("url", "")
    file_id = file_info.get("file_id", "")

    try:
        # 尝试通过 URL 下载
        if file_url and (file_url.startswith("http://") or file_url.startswith("https://")):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                return True

        # 尝试通过 file_id 获取下载链接
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

        # 尝试直接使用 url 中的本地路径
        if file_url and Path(file_url).is_file():
            shutil.copy(file_url, dest)
            return True

    except Exception as e:
        logger.error(f"下载文件失败: {e}")

    return False


async def wait_for_file(
    bot: Bot,
    event: GroupMessageEvent,
    valid_exts: tuple,
    timeout: int = WAIT_FILE_TIMEOUT,
    *,
    cancel_msg: str = " 已取消渲染。",
    timeout_msg: str = " 等待超时，已取消渲染。",
) -> Optional[dict]:
    """
    等待用户在群聊中发送指定后缀的文件。
    返回文件信息 dict，超时或取消返回 None。
    用户发送 "1" 取消/跳过。
    """
    key = (event.group_id, event.user_id)
    evt = asyncio.Event()
    _wait_states[key] = {
        "event": evt,
        "valid_exts": valid_exts,
        "result": None,
    }

    try:
        await asyncio.wait_for(evt.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        _wait_states.pop(key, None)
        await bot.send(event, timeout_msg)
        return None

    state = _wait_states.pop(key, None)
    if not state:
        return None

    result = state.get("result")
    if result is None:
        return None
    if result.get("__cancel__"):
        await bot.send(event, cancel_msg)
        return None
    return result


async def run_mrm_render(
    replay_path: str,
    beatmap_path: str,
    output_dir: str,
    timeout: int = 300,
) -> Optional[Path]:
    """
    调用 ManiaReplayMaster Java 工具渲染回放。
    返回输出视频路径，失败返回 None。
    """
    classpath = str(MRM_DIR.resolve())

    cmd = [
        str(JAVA_EXE),
        "-cp", classpath,
        "me.replaymaster.Main",
    ]

    logger.info(f"[replayrd] 开始渲染: replay={replay_path}, beatmap={beatmap_path}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=output_dir,
        )

        # stdin: beatmap路径 \n replay路径 \n 最后的回车(确认打开视频) \n
        stdin_data = f"{beatmap_path}\n{replay_path}\n\n".encode()
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_data),
            timeout=timeout,
        )

        stdout_str = stdout.decode("gbk", errors="replace")
        stderr_str = stderr.decode("gbk", errors="replace")
        logger.debug(f"[replayrd] stdout:\n{stdout_str}")
        if stderr_str.strip():
            logger.debug(f"[replayrd] stderr:\n{stderr_str}")

        # 检查渲染是否成功（根据中文输出判断）
        if "渲染成功" not in stdout_str and "Render success" not in stdout_str.lower():
            # 尝试从输出中提取错误信息
            error_lines = [l for l in stdout_str.split("\n") if "错误" in l or "Error" in l or "失败" in l]
            if error_lines:
                logger.error(f"[replayrd] 渲染失败: {error_lines}")
            elif proc.returncode != 0:
                logger.error(f"[replayrd] 渲染进程返回非零: {proc.returncode}")
            else:
                logger.error("[replayrd] 未检测到渲染成功标志")
            return None

        # 查找输出的视频文件（Java 工具输出到 out/ 子目录）
        output_dir_path = Path(output_dir)
        video_files = sorted(
            output_dir_path.rglob("*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if video_files:
            logger.info(f"[replayrd] 找到视频: {video_files[0]}")
            return video_files[0]

        logger.error("[replayrd] 未找到输出的视频文件")
        return None

    except asyncio.TimeoutError:
        logger.error(f"[replayrd] 渲染超时 ({timeout}s)")
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except FileNotFoundError:
        logger.error("[replayrd] 未找到 Java 运行环境，请安装 JRE")
        return None
    except Exception as e:
        logger.error(f"[replayrd] 渲染异常: {e}")
        return None


# ==================== /replayrd 指令 ====================

replayrd = on_command("replayrd", block=True,priority=5)


@replayrd.handle()
async def handle_replayrd(bot: Bot, event: MessageEvent):
    # 仅在群聊中支持
    if not isinstance(event, GroupMessageEvent):
        await replayrd.finish("此指令仅在群聊中可用。")

    # 1. 检查是否回复了文件消息
    file_info = get_file_info_from_reply(event)
    if not file_info:
        await replayrd.finish("请回复一个回放文件（.mr / .mrv / .osr）")

    file_name: str = file_info["name"]
    file_lower = file_name.lower()

    # 确定回放类型和需要的谱面后缀
    beatmap_exts: tuple
    if file_lower.endswith(".mrv"):
        replay_type = "mrv"
        beatmap_exts = (".mc", ".mcz")
    elif file_lower.endswith(".mr"):
        replay_type = "mr"
        beatmap_exts = (".mc", ".mcz")
    elif file_lower.endswith(".osr"):
        replay_type = "osr"
        beatmap_exts = (".osu", ".osz")
    else:
        await replayrd.finish(
            f"不支持的文件格式: {file_name}\n请回复 .mr / .mrv / .osr 格式的回放文件。"
        )

    beatmap_exts_hint = " / ".join(beatmap_exts)

    # 2. 创建临时工作目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 3. 下载 replay 文件
        replay_dest = temp_path / file_name
        logger.info(f"[replayrd] 下载回放文件: {file_name}")
        if not await download_file(bot, file_info, replay_dest):
            await replayrd.finish(" 下载回放文件失败，请重试。")

        # 4. 如果是 .mrv，先转换为 .mr
        if replay_type == "mrv":
            await bot.send(event, " 检测到 .mrv 文件，正在转换为 .mr ...")
            mr_name = Path(file_name).stem + ".mr"
            mr_path = temp_path / mr_name
            try:
                ok = await asyncio.to_thread(
                    convert_mrv_to_mr, str(replay_dest), str(mr_path)
                )
                if not ok:
                    await replayrd.finish(" .mrv → .mr 转换失败，请检查文件是否有效。")
                replay_dest = mr_path
                file_name = mr_name
                replay_type = "mr"
                logger.info(f"[replayrd] 转换成功: {mr_path}")
            except Exception as e:
                logger.error(f"[replayrd] 转换异常: {e}")
                await replayrd.finish(f" .mrv → .mr 转换出错: 请反馈bot主人")

        # 5. 要求用户发送谱面文件
        await bot.send(
            event,
            f" 请发送谱面文件（{beatmap_exts_hint}），输入 1 取消。",
        )

        beatmap_info = await wait_for_file(
            bot, event,
            valid_exts=beatmap_exts,
            timeout=WAIT_FILE_TIMEOUT,
        )
        if not beatmap_info:
            return  # wait_for_file 已处理取消/超时消息

        # 6. 下载谱面文件
        bm_name: str = beatmap_info["name"]
        beatmap_dest = temp_path / bm_name
        logger.info(f"[replayrd] 下载谱面文件: {bm_name}")
        if not await download_file(bot, beatmap_info, beatmap_dest):
            await replayrd.finish(" 下载谱面文件失败，请重试。")

        # 7. (可选) 询问用户是否需要提供音频文件
        await bot.send(
            event,
            f"发送音频文件，输入 1 跳过。",
        )
        audio_info = await wait_for_file(
            bot, event,
            valid_exts=(".ogg", ".mp3"),
            timeout=WAIT_FILE_TIMEOUT,
            cancel_msg=" 已跳过音频，继续渲染。",
            timeout_msg=" 等待超时，将跳过音频继续渲染。",
        )
        if audio_info:
            # 下载音频到谱面文件同目录下，命名为 audio.ogg（Java 工具默认查找此名）
            audio_name: str = audio_info["name"]
            audio_dest = temp_path / "audio.ogg"
            logger.info(f"[replayrd] 下载音频文件: {audio_name}")
            if await download_file(bot, audio_info, audio_dest):
                logger.info(f"[replayrd] 音频已保存到: {audio_dest}")
            else:
                await bot.send(event, " 音频下载失败")
        else:
            logger.info("[replayrd] 用户跳过音频文件")

        # 8. 调用 ManiaReplayMaster 渲染
        await bot.send(event, "正在渲染回放视频，请稍候")

        video_path = await run_mrm_render(
            replay_path=str(replay_dest),
            beatmap_path=str(beatmap_dest),
            output_dir=temp_dir,
        )

        if not video_path:
            await replayrd.finish(
                " 渲染失败。"
            )

        # 8. 发送视频
        logger.info(f"[replayrd] 渲染完成: {video_path}")
        try:
            file_size = video_path.stat().st_size
            if file_size > 100 * 1024 * 1024:  # 超过100MB
                await bot.send(event, f" 视频文件过大 ({file_size / 1024 / 1024:.1f} MB)，无法发送。")
            else:
                await bot.upload_group_file(
                    group_id=event.group_id,
                    file=str(video_path),
                    name=video_path.name,
                )
                logger.info(f"[replayrd] 视频已上传到群文件")
        except Exception as e:
            logger.warning(f"[replayrd] 上传群文件失败: {e}")
            try:
                await bot.send(event, MessageSegment.video(f"file:///{video_path}"))
            except Exception as e2:
                logger.error(f"[replayrd] 发送视频失败: {e2}")
                await bot.send(event, f" 发送视频失败: {e2}")
