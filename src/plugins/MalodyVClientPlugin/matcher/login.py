from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.adapters import Message

from .handler.login_handler import process_login, handle_password, pending_logins

# 登录命令
login_cmd = on_command("login", aliases={"登录"}, priority=10, block=True)

@login_cmd.handle()
async def login(bot: Bot, event: Event, args: Message = CommandArg()):
    await process_login(bot, event, args.extract_plain_text().strip())

# 私聊消息监听（用于接收密码）
private_msg = on_message(priority=10, block=False)

@private_msg.handle()
async def on_private_message(bot: Bot, event: PrivateMessageEvent):
    qq = str(event.get_user_id())
    if qq in pending_logins:
        password = event.get_plaintext().strip()
        # 取消超时任务
        pending_logins[qq]["task"].cancel()
        await handle_password(bot, event, qq, password)