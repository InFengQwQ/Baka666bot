import re
import json
import tempfile
import os
from pathlib import Path
from typing import Optional

import httpx
from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.params import CommandArg

# 创建命令，只响应 /解析 或 /parse
parse_cmd = on_command("解析", aliases={"parse"}, block=True, priority=5)

# B站链接正则
BILI_PATTERN = re.compile(
    r"(https?://)?(www\.)?bilibili\.com/video/((BV[0-9A-Za-z]+)|(av\d+))"
    r"|(https?://)?b23\.tv/[0-9A-Za-z]+"
)

# 解析API地址（可换成其他可用接口）
PARSE_API = "https://api.bugpk.com/api/bilibili?url={url}"

# 临时文件目录
TEMP_DIR = Path(tempfile.gettempdir()) / "nonebot_bili_parse"
TEMP_DIR.mkdir(exist_ok=True)

def extract_url_from_text(text: str) -> Optional[str]:
    """从文本中提取B站链接"""
    match = BILI_PATTERN.search(text)
    if match:
        return match.group()
    return None

def extract_url_from_json_card(msg_data: str) -> Optional[str]:
    """从卡片消息的JSON数据中提取链接（适配小程序分享）"""
    try:
        data = json.loads(msg_data)
        if data.get("app") == "com.tencent.miniapp_01":
            meta = data.get("meta", {})
            detail = meta.get("detail_1", {})
            if detail.get("title") == "哔哩哔哩" or detail.get("appName") == "哔哩哔哩":
                qqdocurl = detail.get("qqdocurl", "")
                return extract_url_from_text(qqdocurl)
    except:
        pass
    return None

def get_video_info(url: str) -> Optional[dict]:
    """调用解析API，获取视频信息"""
    try:
        resp = httpx.get(PARSE_API.format(url=url), timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            logger.warning(f"B站解析API返回错误: {data}")
            return None
        return data.get("data")
    except Exception as e:
        logger.error(f"调用解析API失败: {e}")
        return None

async def download_video(video_url: str, title: str) -> Optional[Path]:
    """下载视频到临时文件，返回文件路径"""
    try:
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:30]
        suffix = ".mp4"
        tmp_file = TEMP_DIR / f"{safe_title}_{os.urandom(4).hex()}{suffix}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://www.bilibili.com",
            "Referer": "https://www.bilibili.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "DNT": "1",
        }
        
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", video_url, headers=headers, follow_redirects=True, timeout=120.0) as resp:
                resp.raise_for_status()
                with open(tmp_file, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        return tmp_file
    except Exception as e:
        logger.error(f"视频下载失败: {e}")
        return None
@parse_cmd.handle()
async def handle_parse(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    # 1. 从命令参数中提取链接
    url = extract_url_from_text(arg.extract_plain_text().strip())
    
    # 2. 如果没有链接，检查是否回复了一条消息
    if not url and event.reply:
        reply_msg = event.reply.message
        reply_text = reply_msg.extract_plain_text()
        url = extract_url_from_text(reply_text)
        if not url:
            for seg in reply_msg:
                if seg.type == "json":
                    url = extract_url_from_json_card(seg.data.get("data", ""))
                    if url:
                        break
    
    if not url:
        logger.info("未提取到B站链接，忽略本次命令")
        return

    if not url.startswith("http"):
        url = "https://" + url

    logger.info(f"开始解析B站链接: {url}")
    
    data = get_video_info(url)
    if not data:
        logger.warning("获取视频信息失败")
        return

    video_url = None
    title = data.get("title", "bilibili_video")
    if "videos" in data and data["videos"]:
        first = data["videos"][0]
        video_url = first.get("url")
    else:
        video_url = data.get("url")
    
    if not video_url:
        logger.warning("未能获取到视频直链")
        return

    logger.info(f"视频直链获取成功，开始下载: {video_url}")
    
    video_file = await download_video(video_url, title)
    if not video_file:
        return

    try:
        # 直接传递文件路径字符串，兼容性更好
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_msg(
                group_id=event.group_id,
                message=MessageSegment.video(file=str(video_file.resolve()))
            )
        elif isinstance(event, PrivateMessageEvent):
            await bot.send_private_msg(
                user_id=event.user_id,
                message=MessageSegment.video(file=str(video_file.resolve()))
            )
        logger.info(f"视频发送成功: {title}")
    except Exception as e:
        logger.error(f"发送视频失败: {e}")
    finally:
        try:
            os.remove(video_file)
        except:
            pass