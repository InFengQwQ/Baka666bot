"""帮助图片 — 同步 ma.py HELP_TEXT，删除缓存后重新生成"""
from io import BytesIO
from PIL import Image, ImageDraw

from src.plugin_runtime import osubot_font

async def generate_help_image() -> bytes:
    sections = [
        ("LOGIN & ACCOUNT", ["/login <用户名>", "ma logout", "ma renew", "ma delaccount"]),
        ("PLAYER", ["ma profile [玩家]", "ma search <关键词>", "ma rank [玩家] [模式]", "ma dan [玩家] [模式] [数量]", "ma danall [模式]", "ma friend [数量]", "ma addfriend <UID>", "ma achieve [玩家]", "ma items [玩家]", "ma marlo [玩家]", "ma activity [玩家]", "ma puzzle [玩家]"]),
        ("RANKING", ["/mb [玩家] [模式] [范围]", "ma global [模式] [类型] [数量]", "ma chartrank <CID> [模式] [数量]", "ma eventrank <EID> [数量]"]),
        ("CHARTS & STORE", ["ma store [模式] [数量]", "ma choice [数量]", "ma promote [数量]", "ma chart <CID>", "ma chartlist <SID> [模式] [数量]", "ma chartonline <hash>", "ma song <SID>", "ma wiki <SID> [CID]", "ma skin [模式] [数量]", "ma searchstore <关键词>", "ma download <CID>", "ma friendstore [数量]", "ma storeinfo"]),
        ("CHART OPS (write)", ["ma createchart <SID> <ver> <mode> <level>", "ma createsong <标题> <艺术家>", "ma donate <CID> <金币>", "ma chartpromote <CID> confirm", "ma settype <CID> <类型>", "ma updatehash <CID> <hash>", "ma like <CID>", "ma mychart [玩家] [数量]"]),
        ("COMMUNITY", ["ma comment <CID> [数量]", "ma addcomment <CID> <内容>", "ma delcomment <TID>", "ma review <CID> [数量]", "ma reviewqueue [模式] [数量]", "ma myreview [数量]", "ma reviewcharts <SID>", "ma addreview <CID> <内容>", "ma reviewreply <issue_id> [回复]", "ma reviewaction <id> <action>", "ma reviewstatus <id> <status>", "ma delreview <id>"]),
        ("MISC", ["ma quest", "ma news", "ma event [数量]", "ma mute <UID> confirm", "ma slot <模式> <slots>", "ma skincheck <hash>", "ma buyskin <ID> confirm", "ma help", "/mm"]),
        ("PAGINATION", ["列表命令支持数量：ma store 100, ma dan 50", "自动循环 hasMore/next 达到目标数量", "默认 50 条"]),
    ]

    w, line_h = 720, 20
    total_lines = sum(len(c)+2 for _,c in sections) + 2
    h = total_lines * line_h + 30
    im = Image.new("RGBA", (w, h), (31,41,46,255))
    draw = ImageDraw.Draw(im)

    y = 8
    draw.text((16, y), "MalodyV Bot — 全部命令", font=osubot_font(18), fill=(238,171,0))
    y += 28

    for section, cmds in sections:
        draw.text((10, y), f"  {section}", font=osubot_font(14), fill=(238,171,0))
        y += line_h + 2
        for cmd in cmds:
            draw.text((24, y), cmd, font=osubot_font(12), fill=(102,204,255))
            y += line_h

    bio = BytesIO(); im.convert("RGB").save(bio, "PNG"); return bio.getvalue()
