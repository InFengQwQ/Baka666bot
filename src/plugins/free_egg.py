"""先检查贴蛋：已有则拦截；未贴则贴蛋，并继续后续插件。"""
from nonebot import logger, on_message
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot
from nonebot.matcher import Matcher
from nonebot.rule import Rule

EGG_EMOJI_ID = '188'


def slash_group_message(event: Event) -> bool:
    return (
        isinstance(event, GroupMessageEvent)
        and event.get_plaintext().lstrip().startswith('/')
    )


group_msg = on_message(rule=Rule(slash_group_message), priority=-100, block=False)


@group_msg.handle()
async def handle_group_message(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    # Discord/Telegram 的 OneBot 兼容桥不支持 QQ 贴蛋查询。
    if 'native_bot' in vars(bot):
        return
    if str(event.user_id) == str(bot.self_id):
        matcher.stop_propagation()
        return
    try:
        result = await bot.call_api('get_emoji_likes', message_id=str(event.message_id),
                                    group_id=str(event.group_id), emoji_id=EGG_EMOJI_ID, count=1)
        if not isinstance(result, dict) or not isinstance(result.get('emoji_like_list'), list):
            raise ValueError('Unexpected reaction response')
        if result['emoji_like_list']:
            # Only this matcher instance is blocked, not all future messages.
            matcher.stop_propagation()
            return
        await bot.call_api('set_msg_emoji_like', message_id=event.message_id,
                           emoji_id=EGG_EMOJI_ID, set=True)
    except Exception as error:
        # 保持旧插件的失败行为：贴蛋接口不可用时不影响正常指令。
        logger.debug('free_egg: reaction API unavailable ({})', type(error).__name__)
