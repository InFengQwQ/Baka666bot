"""ma help - 查看帮助图片"""
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment
from nonebot.log import logger
import os
from pathlib import Path

from src.storage import plugin_data
HELP_IMG = plugin_data("MalodyVClientPlugin") / "cache" / "ma_help.png"


async def handle(bot: Bot, event: Event, args: str):
    if HELP_IMG.exists():
        await bot.send(event, MessageSegment.image(HELP_IMG.read_bytes()))
        return
    try:
        from ...render.help_image import generate_help_image
        img_bytes = await generate_help_image()
        HELP_IMG.parent.mkdir(parents=True, exist_ok=True)
        HELP_IMG.write_bytes(img_bytes)
        await bot.send(event, MessageSegment.image(img_bytes))
    except Exception as e:
        logger.error(f"生成帮助图片失败: {e}")
        await bot.send(event, "帮助图片生成失败，请稍后重试")
