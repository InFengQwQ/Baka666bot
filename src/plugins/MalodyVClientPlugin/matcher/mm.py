from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Bot, Event

from .handler.mm_handler import process_mm

mm_cmd = on_command("mm", aliases={"MM"}, priority=5)


@mm_cmd.handle()
async def handle_mm(bot: Bot, event: Event, args: Message = CommandArg()):
    # 参数提取与校验全部交给 handler
    reply = process_mm(args.extract_plain_text().strip())
    # 如果 handler 返回了消息，则发送
    if reply:
        await bot.send(event, reply)