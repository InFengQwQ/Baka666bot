from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg
from .handler.mmbest_handler import process_best

best_cmd = on_command("mb", aliases={"mmbest", "mmb", "mabest"}, priority=10, block=True)

@best_cmd.handle()
async def handle_best(bot: Bot, event: Event, args: Message = CommandArg()):
    await process_best(bot, event, args.extract_plain_text().strip())