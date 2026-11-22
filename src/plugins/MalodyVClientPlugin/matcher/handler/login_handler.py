import asyncio
import uuid
from nonebot.adapters.onebot.v11 import Bot, Event, PrivateMessageEvent
from nonebot.log import logger

from ...MalodyAPI.account.login import malody_login
from ...MalodyAPI.database import db
from .login_exist_check import check_username_exists, get_username_by_uid

# 待登录状态队列 {qq: {"username": str, "task": asyncio.Task, "event": Event, "uid_hint": str|None}}
pending_logins = {}


async def process_login(bot: Bot, event: Event, args: str):
    qq = str(event.get_user_id())
    plain = args.strip().split()
    if not plain:
        await bot.send(event, "格式：/login <用户名> 或 /login #uid")
        return

    target = plain[0]
    is_uid = target.startswith('#') and target[1:].isdigit()
    if is_uid:
        uid = target[1:]
        username = await get_username_by_uid(int(uid))
        if not username:
            await bot.send(event, "暂不支持通过 UID 查找用户")
            return
    else:
        username = target
        if not await check_username_exists(username):
            await bot.send(event, "玩家不存在")
            return
        uid = None

    # 提示私信密码
    await bot.send(event, f"请30秒内**私聊**发送密码")
    task = asyncio.create_task(_cancel_login(bot, qq, event))
    pending_logins[qq] = {
        "username": username,
        "task": task,
        "event": event,
        "uid_hint": uid
    }


async def _cancel_login(bot: Bot, qq: str, trigger_event: Event):
    await asyncio.sleep(30)
    pending = pending_logins.pop(qq, None)
    if pending:
        await bot.send(trigger_event, "超时已取消登录")


async def handle_password(bot: Bot, event: PrivateMessageEvent, qq: str, password: str):
    pending = pending_logins.pop(qq, None)
    if not pending:
        return

    username = pending["username"]
    device_id = f"qq-{qq}-{uuid.uuid4().hex[:8]}"
    existing_uid = await db.get_uid_by_qq(qq)
    if existing_uid:
        user = await db.get_user(existing_uid)
        if user and user.get("device_id"):
            device_id = user["device_id"]

    try:
        result = await asyncio.to_thread(malody_login, username, password, device_id)
    except Exception as e:
        logger.error(f"登录请求异常: {e}")
        await bot.send(event, f"登录失败：请反馈bot主人")
        return

    if result.get("code") != 0:
        msg = result.get("msg", "未知错误")
        await bot.send(event, f"登录失败：{msg}")
        return

    try:
        uid = str(result["uid"])
        await db.save_user(
            uid=uid,
            device_id=device_id,
            store_token=result["tokenStore"],
            access_token=result["token"],
            username=result.get("username"),
            avatar=result.get("avatar"),
            gold=result.get("gold"),
            tcp_server=result.get("tcp"),
            group_list=result.get("group"),
            is_login=True
        )
        await db.bind_qq(uid, qq)
        await bot.send(event, f"登录成功！\nUID: {uid}\n用户名: {result['username']}")
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        await bot.send(event, f"登录成功但保存失败：请反馈bot主人")