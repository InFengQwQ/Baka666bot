"""ma renew - 刷新令牌"""
import asyncio
from nonebot.adapters.onebot.v11 import Bot, Event
from .user_utils import get_user_creds
from ...MalodyAPI.account.renew import renew_token
from ...MalodyAPI.database import db


async def handle(bot: Bot, event: Event, args: str):
    qq = str(event.get_user_id())
    uid, user = await get_user_creds(qq)
    if not user:
        await bot.send(event, "请先 /login 登录")
        return
    try:
        r = await asyncio.to_thread(renew_token, access_token=user["access_token"], uid=uid)
        if r.get("code") == 0:
            new_token = r.get("token", user["access_token"])
            await db.save_user(uid=uid, device_id=user["device_id"], store_token=user.get("store_token", ""), access_token=new_token, is_login=True)
            await bot.send(event, "令牌已刷新")
        else:
            await bot.send(event, "刷新失败，请重新 /login")
    except Exception:
        await bot.send(event, "刷新失败")
