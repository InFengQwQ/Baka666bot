from nonebot import on_command
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment
acc_cmd = on_command("acc", aliases={"/acc"})
@acc_cmd.handle()
async def handle_acc(bot: Bot, event: Event):
    url = "https://uzxn.github.io/acc/"
    await acc_cmd.finish(url)