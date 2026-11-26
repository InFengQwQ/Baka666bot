from src.plugin_runtime import required_malody_account, malody_web_cookies, osubot_font
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment
from nonebot.log import logger
import httpx
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw
import traceback
import re
from bs4 import BeautifulSoup
import time

# ---------- Malody 配置 ----------
PLAYER_RANK_URL = "https://m.mugzone.net/page/all/player"

# 命令注册
exptop_cmd = on_command("exptop",priority=10, block=True)
mmtop_cmd = on_command("mmtop", priority=10, block=True)

# ---------- 辅助函数 ----------
async def download_img(url: str, size=None):
    if not url:
        return None
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content)).convert("RGBA")
                if size:
                    img = img.resize(size, Image.LANCZOS)
                return img
        except:
            pass
    return None

def draw_fillet(img: Image.Image, radius: int):
    circle = Image.new("L", (radius*2, radius*2), 0)
    ImageDraw.Draw(circle).ellipse((0, 0, radius*2, radius*2), fill=255)
    img = img.convert("RGBA")
    w, h = img.size
    alpha = Image.new("L", img.size, 255)
    alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
    alpha.paste(circle.crop((radius, 0, radius*2, radius)), (w-radius, 0))
    alpha.paste(circle.crop((radius, radius, radius*2, radius*2)), (w-radius, h-radius))
    alpha.paste(circle.crop((0, radius, radius, radius*2)), (0, h-radius))
    img.putalpha(alpha)
    return img

def get_acc_color(acc: float):
    if acc >= 99:   return (255, 215, 0)
    elif acc >= 97: return (103, 240, 171)
    elif acc >= 95: return (217, 240, 103)
    elif acc >= 90: return (240, 194, 103)
    else:           return (240, 102, 102)

# ---------- 字体加载 ----------
f_title = osubot_font(72)
f_info  = osubot_font(46)
f_head  = osubot_font(38)
f_row   = osubot_font(36)
f_acc   = osubot_font(34)
f_sml   = osubot_font(30)

# ---------- Exp排行榜数据抓取 ----------
async def fetch_web_top50() -> list:
    """从网页抓取玩家总榜前50（含等级/经验/游玩/Combo）"""
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": "; ".join(k + "=" + v for k, v in (await malody_web_cookies()).items()), "Accept-Language": "zh-CN,zh;q=0.9"}
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(PLAYER_RANK_URL, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'lxml')

    records = []
    # 前三名
    for div in soup.select("div.item-top"):
        rec = {}
        label = div.select_one("i.label")
        if label:
            cls = label.get("class", [])
            for c in cls:
                if c.startswith("top-"):
                    rec["rank"] = int(c.split("-")[1])
                    break
        if "rank" not in rec:
            rec["rank"] = 1
        avatar = div.select_one("span.avatar img")
        rec["avatar_url"] = avatar["src"] if avatar else ""
        name_a = div.select_one("span.name a")
        rec["name"] = name_a.get_text(strip=True) if name_a else ""
        lv_span = div.select_one("span.lv")
        if lv_span:
            m = re.search(r"Lv\.(\d+)\s*-\s*([\d,]+)", lv_span.get_text(strip=True))
            if m:
                rec["lv"] = int(m.group(1))
                rec["exp"] = int(m.group(2).replace(",", ""))
        acc_span = div.select_one("span.acc")
        rec["acc"] = float(acc_span.get_text(strip=True).replace("Acc:", "").replace("%", "")) if acc_span else 0.0
        combo_span = div.select_one("span.combo")
        rec["combo"] = int(combo_span.get_text(strip=True).replace("Combo:", "").replace(",", "")) if combo_span else 0
        pc_span = div.select_one("span.pc")
        rec["play_count"] = int(pc_span.get_text(strip=True).replace("游玩次数:", "").replace(",", "")) if pc_span else 0
        records.append(rec)

    # 4~50名
    for item in soup.select("div.item")[:47]:
        rec = {}
        rank_span = item.select_one("span.rank")
        rec["rank"] = int(rank_span.get_text(strip=True)) if rank_span else len(records)+1
        avatar = item.select_one("span.avatar img")
        rec["avatar_url"] = avatar["src"] if avatar else ""
        name_a = item.select_one("span.name a")
        rec["name"] = name_a.get_text(strip=True) if name_a else ""
        lv_span = item.select_one("span.lv")
        rec["lv"] = int(lv_span.get_text(strip=True)) if lv_span else 1
        exp_span = item.select_one("span.exp")
        rec["exp"] = int(exp_span.get_text(strip=True).replace(",", "")) if exp_span else 0
        acc_span = item.select_one("span.acc")
        rec["acc"] = float(acc_span.get_text(strip=True).replace("%", "")) if acc_span else 0.0
        pc_span = item.select_one("span.pc")
        rec["play_count"] = int(pc_span.get_text(strip=True).replace(",", "")) if pc_span else 0
        combo_span = item.select_one("span.combo")
        rec["combo"] = int(combo_span.get_text(strip=True).replace(",", "")) if combo_span else 0
        records.append(rec)

    return records[:50]

async def fetch_api_top100() -> list:
    """从 API 获取前100名基础数据（score/acc）"""
    headers = {"User-Agent": "Malody 6.6.43"}
    account_uid, account_key = await required_malody_account()
    results = []
    async with httpx.AsyncClient(verify=False) as client:
        for offset in [0, 40, 80]:
            t = int(time.time())
            url = f"https://api.mugzone.net/api/ranking/global?key={account_key}&uid={account_uid}&mode=0&from={offset}&t={t}"
            resp = await client.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and isinstance(data["data"], list):
                    results.extend(data["data"])
    return results[:100]

async def merge_top100():
    web = await fetch_web_top50()
    api = await fetch_api_top100()
    api_dict = {item.get("rank", 0): item for item in api}
    merged = []

    for i in range(1, 101):
        web_rec = next((x for x in web if x["rank"] == i), None)
        api_rec = api_dict.get(i, {})
        rec = {
            "rank": i,
            "username": web_rec["name"] if web_rec else api_rec.get("username", "?"),
            "avatar_url": web_rec["avatar_url"] if web_rec else f"https://cni.machart.top/avatar/{api_rec.get('uid')}!avatar",
            "score": int(api_rec.get("value", 0)),
            "acc": web_rec["acc"] if web_rec else api_rec.get("acc", 0),
            "lv": web_rec.get("lv") if web_rec else None,
            "exp": web_rec.get("exp") if web_rec else None,
            "play_count": web_rec.get("play_count") if web_rec else None,
            "combo": web_rec.get("combo") if web_rec else None,
        }
        merged.append(rec)
    return merged

# ---------- 绘制Exp排行榜图片 ----------
async def draw_global_top100(records: list) -> bytes:
    width = 1920
    head_h = 300
    row_h = 160
    bottom_pad = 60
    total_h = head_h + len(records) * row_h + bottom_pad

    im = Image.new("RGBA", (width, total_h), (25, 30, 35, 255))
    draw = ImageDraw.Draw(im)

    # 标题区
    draw.rectangle([(0, 0), (width, head_h)], fill=(20, 24, 28, 255))
    draw.text((width//2, 100), "Malody 全球玩家排行榜 Top100", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((width//2, 180), "Key 模式 · 总榜", font=f_info, fill=(200, 200, 200), anchor="mm")
    draw.line([(60, head_h-40), (width-60, head_h-40)], fill=(255, 255, 255, 80), width=2)

    # 表头
    cols = [50, 130, 270, 540, 760, 1160, 1430, 1630, 1920]
    heads = ["#", "", "Player", "Score", "Lv.        EXP", "  Acc%", " PC", "Combo"]
    for i, h in enumerate(heads):
        if i == 1: continue
        draw.text((cols[i], head_h-15), h, font=f_head, fill=(255, 210, 120), anchor="lm")

    # 下载头像
    avatar_tasks = [download_img(r.get("avatar_url"), (100, 100)) for r in records]
    avatars = await asyncio.gather(*avatar_tasks)

    for i, rec in enumerate(records):
        y = head_h + i * row_h
        bg = (45, 55, 60, 80) if i % 2 == 0 else (35, 45, 50, 50)
        draw.rectangle([30, y, width-30, y+row_h-5], fill=bg)
        cy = y + row_h//2 + 4

        # 排名
        rank = rec["rank"]
        rank_color = (255, 215, 0) if rank == 1 else (192, 192, 192) if rank == 2 else (205, 127, 50) if rank == 3 else (255, 255, 255)
        draw.text((cols[0], cy), str(rank), font=f_row, fill=rank_color, anchor="lm")

        # 头像
        av = avatars[i] if isinstance(avatars[i], Image.Image) else None
        if av:
            av = draw_fillet(av, 15)
            im.alpha_composite(av, (cols[1], y + (row_h-100)//2))

        # 昵称
        name = rec.get("username", "?")
        if len(name) > 9: name = name[:8] + "…"
        draw.text((cols[2], cy), name, font=f_row, fill=(255, 255, 255), anchor="lm")

        # 分数
        score = rec.get("score", 0)
        draw.text((cols[3], cy), f"{score:,}", font=f_row, fill=(255, 255, 255), anchor="lm")

        # 等级/经验
        lv = rec.get("lv")
        exp = rec.get("exp")
        if lv is not None and exp is not None:
            lv_text = f"Lv.{lv}    {exp:,}"
        else:
            lv_text = "-"
        draw.text((cols[4], cy), lv_text, font=f_sml, fill=(200, 200, 200), anchor="lm")

        # Acc 进度条
        acc = rec.get("acc", 0)
        color = get_acc_color(acc)
        bar_w, bar_h = 180, 44
        bx, by = cols[5], cy - bar_h//2
        draw.rounded_rectangle([bx, by, bx+bar_w, by+bar_h], radius=10, fill=(30, 30, 30, 160))
        fw = int(bar_w * min(acc, 100) / 100)
        if fw > 0:
            draw.rounded_rectangle([bx, by, bx+fw, by+bar_h], radius=10, fill=color)
        draw.text((bx+bar_w/2+2, by+bar_h/2+2), f"{acc:.2f}%", font=f_acc, fill=(0, 0, 0, 160), anchor="mm")
        draw.text((bx+bar_w/2, by+bar_h/2), f"{acc:.2f}%", font=f_acc, fill=(255, 255, 255), anchor="mm")

        # 游玩次数
        play = rec.get("play_count")
        play_text = f"{play:,}" if play is not None else "-"
        draw.text((cols[6], cy), play_text, font=f_row, fill=(200, 200, 200), anchor="lm")

        # Combo
        combo = rec.get("combo")
        combo_text = f"{combo:,}x" if combo is not None else "-"
        draw.text((cols[7], cy), combo_text, font=f_row, fill=(255, 255, 100), anchor="lm")

    buf = BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()

# ---------- mm排行榜数据抓取 ----------
async def fetch_mm_top100() -> list:
    """从 Malody API 获取 mm 模式全球前100数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    account_uid, account_key = await required_malody_account()
    all_data = []
    async with httpx.AsyncClient(verify=False) as client:
        for offset in [0, 40, 80]:
            params = {
                "mm": "1",
                "mode": "0",
                "from": str(offset),
                "ver": "0",
                "key": account_key,
                "uid": str(account_uid),
            }
            resp = await client.get(
                "https://api.mugzone.net/api/ranking/global",
                params=params,
                headers=headers,
                timeout=15
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if data.get("code") == 0 and isinstance(data.get("data"), list):
                all_data.extend(data["data"])
    all_data.sort(key=lambda x: x.get("rank", 9999))
    top100 = all_data[:100]

    records = []
    for item in top100:
        uid = item.get("uid")
        avatar_url = f"https://cni.machart.top/avatar/{uid}!avatar" if uid else ""

        records.append({
            "rank": item.get("rank", 0),
            "username": item.get("username", "?"),
            "avatar_url": avatar_url,
            "score": int(item.get("value", 0)),
            "level": int(item.get("level", 1)),
            "acc": float(item.get("acc", 0)),
            "play_count": int(item.get("playcount", 0)),
            "combo": int(item.get("combo", 0)),
        })
    return records

# ---------- 绘制mm排行榜图片 ----------
async def draw_mm_top100(records: list) -> bytes:
    width = 1920
    head_h = 300
    row_h = 160
    bottom_pad = 60
    total_h = head_h + len(records) * row_h + bottom_pad

    im = Image.new("RGBA", (width, total_h), (25, 30, 35, 255))
    draw = ImageDraw.Draw(im)

    draw.rectangle([(0, 0), (width, head_h)], fill=(20, 24, 28, 255))
    draw.text((width//2, 100), "Malody mm 模式排行榜 Top100", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((width//2, 180), "Key · mm 总榜", font=f_info, fill=(200, 200, 200), anchor="mm")
    draw.line([(60, head_h-40), (width-60, head_h-40)], fill=(255, 255, 255, 80), width=2)

    cols = [50, 130, 270, 580, 850, 1080, 1320, 1520, 1920]
    heads = ["#", "", "Player", "MM", "Level", "  Acc%", " PC", "Combo"]
    for i, h in enumerate(heads):
        if i == 1:
            continue
        draw.text((cols[i], head_h-15), h, font=f_head, fill=(255, 210, 120), anchor="lm")

    avatar_tasks = [download_img(r.get("avatar_url"), (100, 100)) for r in records]
    avatars = await asyncio.gather(*avatar_tasks)

    for i, rec in enumerate(records):
        y = head_h + i * row_h
        bg = (45, 55, 60, 80) if i % 2 == 0 else (35, 45, 50, 50)
        draw.rectangle([30, y, width-30, y+row_h-5], fill=bg)
        cy = y + row_h//2 + 4

        rank = rec["rank"]
        rank_color = (255, 215, 0) if rank == 1 else (192, 192, 192) if rank == 2 else (205, 127, 50) if rank == 3 else (255, 255, 255)
        draw.text((cols[0], cy), str(rank), font=f_row, fill=rank_color, anchor="lm")

        av = avatars[i] if isinstance(avatars[i], Image.Image) else None
        if av:
            av = draw_fillet(av, 15)
            im.alpha_composite(av, (cols[1], y + (row_h-100)//2))

        name = rec.get("username", "?")
        if len(name) > 9: name = name[:8] + "…"
        draw.text((cols[2], cy), name, font=f_row, fill=(255, 255, 255), anchor="lm")

        score = rec.get("score", 0)
        draw.text((cols[3], cy), f"{score:,}", font=f_row, fill=(255, 255, 255), anchor="lm")

        level = rec.get("level", 0)
        draw.text((cols[4], cy), f"Lv.{level}", font=f_row, fill=(200, 200, 200), anchor="lm")

        acc = rec.get("acc", 0)
        color = get_acc_color(acc)
        bar_w, bar_h = 180, 44
        bx, by = cols[5], cy - bar_h//2
        draw.rounded_rectangle([bx, by, bx+bar_w, by+bar_h], radius=10, fill=(30, 30, 30, 160))
        fw = int(bar_w * min(acc, 100) / 100)
        if fw > 0:
            draw.rounded_rectangle([bx, by, bx+fw, by+bar_h], radius=10, fill=color)
        draw.text((bx+bar_w/2+2, by+bar_h/2+2), f"{acc:.2f}%", font=f_acc, fill=(0, 0, 0, 160), anchor="mm")
        draw.text((bx+bar_w/2, by+bar_h/2), f"{acc:.2f}%", font=f_acc, fill=(255, 255, 255), anchor="mm")

        play = rec.get("play_count")
        play_text = f"{play:,}" if play is not None else "-"
        draw.text((cols[6], cy), play_text, font=f_row, fill=(200, 200, 200), anchor="lm")

        combo = rec.get("combo")
        combo_text = f"{combo:,}x" if combo is not None else "-"
        draw.text((cols[7], cy), combo_text, font=f_row, fill=(255, 255, 100), anchor="lm")

    buf = BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()

# ---------- 命令处理 ----------
@exptop_cmd.handle()
async def handle_exptop(bot: Bot, event: Event):
    try:
        records = await merge_top100()
    except Exception as e:
        logger.error(f"排行榜获取失败: {traceback.format_exc()}")
        #await exptop_cmd.finish("排行榜数据获取失败，请稍后再试。")
        return

    if not records:
        #await exptop_cmd.finish("无数据。")
        return

    try:
        img_bytes = await draw_global_top100(records)
        await exptop_cmd.send(MessageSegment.image(img_bytes))
    except Exception as e:
        logger.error(f"绘图失败: {traceback.format_exc()}")
        #await exptop_cmd.finish("图片生成失败，请检查后台日志。")

@mmtop_cmd.handle()
async def handle_mmtop(bot: Bot, event: Event):
    try:
        records = await fetch_mm_top100()
    except Exception as e:
        logger.error(f"mm 排行榜获取失败: {traceback.format_exc()}")
        #await mmtop_cmd.finish("mm 排行榜数据获取失败，请稍后再试。")
        return

    if not records:
        #await mmtop_cmd.finish("无数据。")
        return

    try:
        img_bytes = await draw_mm_top100(records)
        await mmtop_cmd.send(MessageSegment.image(img_bytes))
    except Exception as e:
        logger.error(f"绘图失败: {traceback.format_exc()}")
        #await mmtop_cmd.finish("图片生成失败，请检查后台日志。")
