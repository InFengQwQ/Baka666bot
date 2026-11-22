"""
/mrv2mr - 将 .mrv 回放文件转换为 .mr 格式
回复 .mrv 文件并发送 /mrv2mr 来转换
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.log import logger

from .mrv2mr import convert_mrv_to_mr


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


# ==================== /mrv2mr 指令 ====================

mrv2mr_cmd = on_command("mrv2mr", block=True,priority=5)


@mrv2mr_cmd.handle()
async def handle_mrv2mr(bot: Bot, event: MessageEvent):
    # 1. 检查是否回复了文件消息
    file_info = get_file_info_from_reply(event)
    if not file_info:
        await mrv2mr_cmd.finish("请回复一个 .mrv 文件再使用此指令。")

    file_name: str = file_info["name"]
    if not file_name.lower().endswith(".mrv"):
        await mrv2mr_cmd.finish(
            f"不支持的文件格式: {file_name}\n请回复 .mrv 格式的回放文件。"
        )

    # 2. 创建工作目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 3. 下载 .mrv 文件
        mrv_dest = temp_path / file_name
        logger.info(f"[mrv2mr] 下载文件: {file_name}")
        if not await download_file(bot, file_info, mrv_dest):
            await mrv2mr_cmd.finish("❌ 下载文件失败，请重试。")

        # 4. 转换为 .mr
        mr_name = Path(file_name).stem + ".mr"
        mr_path = temp_path / mr_name

        try:
            ok = await asyncio.to_thread(
                convert_mrv_to_mr, str(mrv_dest), str(mr_path)
            )
            if not ok:
                await mrv2mr_cmd.finish("❌ 转换失败，请检查 .mrv 文件是否有效。")
        except Exception as e:
            logger.error(f"[mrv2mr] 转换异常: {e}")
            await mrv2mr_cmd.finish(f"❌ 转换出错: 请反馈bot主人")

        if not mr_path.exists():
            await mrv2mr_cmd.finish("❌ 转换失败，未生成 .mr 文件。")

        logger.info(f"[mrv2mr] 转换成功: {mr_path} (size={mr_path.stat().st_size})")

        # 5. 发送 .mr 文件
        if isinstance(event, GroupMessageEvent):
            try:
                await bot.upload_group_file(
                    group_id=event.group_id,
                    file=str(mr_path),
                    name=mr_name,
                )
                logger.info(f"[mrv2mr] 文件已上传到群文件")
            except Exception as e:
                logger.warning(f"[mrv2mr] 上传群文件失败: {e}")
                await mrv2mr_cmd.finish(f"❌ 发送文件失败: 请反馈bot主人")
        elif isinstance(event, PrivateMessageEvent):
            try:
                await bot.upload_private_file(
                    user_id=event.user_id,
                    file=str(mr_path),
                    name=mr_name,
                )
                logger.info(f"[mrv2mr] 文件已私发")
            except Exception as e:
                logger.warning(f"[mrv2mr] 私发文件失败: {e}")
                await mrv2mr_cmd.finish(f"❌ 发送文件失败: 请反馈bot主人")