"""ma 主命令调度器 — 所有子命令统一入口，均需登录。支持 p<页码> 翻页参数。"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot.log import logger

from .handler import ma_help, ma_profile, ma_search, ma_rank, ma_dan
from .handler import ma_global, ma_store, ma_event, ma_chart, ma_friend
from .handler import ma_achieve, ma_quest, ma_news, ma_song, ma_wiki, ma_logout
from .handler import ma_items, ma_marlo, ma_activity, ma_chartrank, ma_eventrank
from .handler import ma_puzzle, ma_choice, ma_promote, ma_skin, ma_comment
from .handler import ma_review, ma_reviewqueue, ma_myreview, ma_mychart
from .handler import ma_chartonline, ma_danall, ma_chartlist, ma_addfriend, ma_like
from .handler import ma_createchart, ma_donate, ma_chartpromote, ma_settype, ma_updatehash
from .handler import ma_createsong, ma_addcomment, ma_delcomment
from .handler import ma_addreview, ma_reviewaction, ma_reviewcharts, ma_reviewreply, ma_delreview, ma_reviewstatus
from .handler import ma_delaccount, ma_renew, ma_storeinfo, ma_searchstore, ma_download, ma_friendstore
from .handler import ma_mute, ma_skincheck, ma_buyskin, ma_slot

ma_cmd = on_command("ma", aliases={"MA", "Ma", "malody"}, priority=5, block=True)

_SUBCOMMANDS = {
    "help": ma_help, "profile": ma_profile, "search": ma_search,
    "rank": ma_rank, "dan": ma_dan, "global": ma_global,
    "store": ma_store, "event": ma_event, "chart": ma_chart,
    "friend": ma_friend, "achieve": ma_achieve, "quest": ma_quest,
    "news": ma_news, "song": ma_song, "wiki": ma_wiki, "logout": ma_logout,
    "items": ma_items, "marlo": ma_marlo, "activity": ma_activity,
    "chartrank": ma_chartrank, "eventrank": ma_eventrank,
    "puzzle": ma_puzzle, "choice": ma_choice, "promote": ma_promote,
    "skin": ma_skin, "comment": ma_comment, "review": ma_review,
    "reviewqueue": ma_reviewqueue, "myreview": ma_myreview,
    "mychart": ma_mychart, "chartonline": ma_chartonline,
    "danall": ma_danall, "chartlist": ma_chartlist,
    "addfriend": ma_addfriend, "like": ma_like,
    # 写操作
    "createchart": ma_createchart, "donate": ma_donate,
    "chartpromote": ma_chartpromote, "settype": ma_settype, "updatehash": ma_updatehash,
    "createsong": ma_createsong, "addcomment": ma_addcomment, "delcomment": ma_delcomment,
    "addreview": ma_addreview, "reviewaction": ma_reviewaction,
    "reviewcharts": ma_reviewcharts, "reviewreply": ma_reviewreply,
    "delreview": ma_delreview, "reviewstatus": ma_reviewstatus,
    "delaccount": ma_delaccount, "renew": ma_renew,
    "storeinfo": ma_storeinfo, "searchstore": ma_searchstore,
    "download": ma_download, "friendstore": ma_friendstore,
    "mute": ma_mute, "skincheck": ma_skincheck, "buyskin": ma_buyskin,
    "slot": ma_slot,
}

HELP_TEXT = """MalodyV Bot (v2) — 所有命令均需登录
━━ 信息查询 ━━
ma profile/search/rank/dan/danall/friend
ma achieve/items/marlo/activity/puzzle
ma chart/song/wiki/chartonline
ma store/choice/promote/skin/download
ma news/quest/event/storeinfo
━━ 排行 ━━
ma global/chartrank/eventrank
━━ 列表翻页 ━━
ma store p2 | ma skin p3
ma comment <CID> p2 | ma friend p2
━━ 社交换作 ━━
ma addfriend/like/addcomment/delcomment
ma addreview/reviewreply/delreview
ma donate <CID> <金币>
━━ 谱面管理 ━━
ma createchart/createsong/chartpromote
ma settype/updatehash/mychart
━━ 审核 ━━
ma review/reviewqueue/myreview
ma reviewcharts/reviewaction/reviewstatus
━━ 商店搜索 ━━
ma searchstore <关键词>
ma friendstore
━━ 账号 ━━
ma logout/renew/delaccount
ma mute/slot/skincheck/buyskin
━━ 其他 ━━
/login | /mb | /mm | ma help"""


@ma_cmd.handle()
async def handle_ma(bot: Bot, event: Event, args: Message = CommandArg()):
    plain = args.extract_plain_text().strip()
    if not plain:
        await bot.send(event, HELP_TEXT)
        return
    parts = plain.split(maxsplit=1)
    subcmd = parts[0].lower()
    subargs = parts[1] if len(parts) > 1 else ""
    handler = _SUBCOMMANDS.get(subcmd)
    if not handler:
        await bot.send(event, f"未知命令: {subcmd}，输入 ma 查看命令列表")
        return
    try:
        await handler.handle(bot, event, subargs)
    except Exception as e:
        logger.error(f"执行 ma {subcmd} 失败: {e}")
