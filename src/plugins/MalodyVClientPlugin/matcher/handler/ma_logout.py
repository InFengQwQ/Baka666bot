"""ma logout - 登出账号"""
import asyncio
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.log import logger
from .user_utils import get_user_creds
from ...MalodyAPI.account.logout import malody_logout
from ...MalodyAPI.database import db


async def handle(bot: Bot, event: Event, args: str):
    qq = str(event.get_user_id())
    uid, user = await get_user_creds(qq)
    if not user:
        await bot.send(event, "你尚未登录")
        return

    try:
        await asyncio.to_thread(malody_logout, access_token=user["access_token"], uid=uid)
    except Exception as e:
        logger.warning(f"服务器登出失败（继续清理本地数据）: {e}")

    try:
        await db.save_user(
            uid=uid,
            device_id=user.get("device_id", ""),
            store_token=user.get("store_token", ""),
            access_token=None,
            is_login=False,
        )
        await bot.send(event, "已登出")
    except Exception as e:
        logger.error(f"清理本地数据失败: {e}")
        await bot.send(event, "登出失败")
