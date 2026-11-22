"""ma delaccount - 注销账号（二次确认）"""
from nonebot.adapters.onebot.v11 import Bot, Event
from .user_utils import get_user_creds
from ...MalodyAPI.account.deletion import delete_account
from ...MalodyAPI.database import db

_CONFIRM = {}


async def handle(bot: Bot, event: Event, args: str):
    qq = str(event.get_user_id())
    uid, user = await get_user_creds(qq)
    if not user:
        await bot.send(event, "请先 /login 登录")
        return
    if args.strip() == "confirm":
        try:
            await __import__("asyncio").to_thread(delete_account, access_token=user["access_token"], uid=uid)
            await db.save_user(uid=uid, device_id=user.get("device_id", ""), store_token=user.get("store_token", ""), access_token=None, is_login=False)
            await bot.send(event, "账号已注销")
        except Exception as e:
            await bot.send(event, "注销失败")
        return
    await bot.send(event, "⚠️ 此操作不可撤销！输入 ma delaccount confirm 确认注销")
