import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import httpx
from pathlib import Path

# ---------- 字体配置 ----------
import nonebot
from importlib.util import find_spec
_spec = find_spec("nonebot_plugin_osubot")
plugin_dir = (Path(_spec.origin).parent / "nonebot_plugin_osubot" if _spec.origin.endswith(".pyd") else Path(_spec.origin).parent) if _spec and _spec.origin else Path(__file__).parent
font_dir = plugin_dir / "osufile" / "fonts"

# 字体大小整体大幅放大
if font_dir.exists():
    f_title = ImageFont.truetype(str(font_dir / "Torus SemiBold.otf"), 72)
    f_info  = ImageFont.truetype(str(font_dir / "Torus Regular.otf"), 46)
    f_head  = ImageFont.truetype(str(font_dir / "Torus SemiBold.otf"), 38)
    f_row   = ImageFont.truetype(str(font_dir / "Torus Regular.otf"), 36)
    f_acc   = ImageFont.truetype(str(font_dir / "Torus SemiBold.otf"), 34)
    f_sml   = ImageFont.truetype(str(font_dir / "Torus Regular.otf"), 30)
else:
    try:
        f_title = ImageFont.truetype("msyh.ttc", 72)
        f_info  = ImageFont.truetype("msyh.ttc", 46)
        f_head  = ImageFont.truetype("msyh.ttc", 38)
        f_row   = ImageFont.truetype("msyh.ttc", 36)
        f_acc   = ImageFont.truetype("msyh.ttc", 34)
        f_sml   = ImageFont.truetype("msyh.ttc", 30)
    except:
        f_title = f_info = f_head = f_row = f_acc = f_sml = ImageFont.load_default()

# ---------- 颜色配置 ----------
ACC_COLORS = {
    "color-0": (103, 240, 171),
    "color-1": (217, 240, 103),
    "color-2": (240, 194, 103),
    "color-3": (240, 149, 103),
    "color-4": (239, 102, 102),
}
DEFAULT_ACC_COLOR = ACC_COLORS["color-4"]

def get_acc_color(color_class: str):
    return ACC_COLORS.get(color_class, DEFAULT_ACC_COLOR)

# ---------- Mod 图标 ----------
MOD_ICON_BASE = "https://m.mugzone.net/static/img/mod/"
_mod_cache = {}

async def download_mod_icon(cls: str):
    if cls in _mod_cache:
        return _mod_cache[cls]
    num = cls.replace('g_mod_', '')
    url = f"{MOD_ICON_BASE}mod-{num}.png"
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(url, timeout=5)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content)).convert("RGBA").resize((64, 64))
                _mod_cache[cls] = img
                return img
        except:
            pass
    return None

# ---------- 辅助函数 ----------
def draw_fillet(img, r):
    circle = Image.new("L", (r*2, r*2), 0)
    ImageDraw.Draw(circle).ellipse((0,0,r*2,r*2), fill=255)
    img = img.convert("RGBA")
    w, h = img.size
    alpha = Image.new("L", img.size, 255)
    alpha.paste(circle.crop((0,0,r,r)), (0,0))
    alpha.paste(circle.crop((r,0,r*2,r)), (w-r,0))
    alpha.paste(circle.crop((r,r,r*2,r*2)), (w-r,h-r))
    alpha.paste(circle.crop((0,r,r,r*2)), (0,h-r))
    img.putalpha(alpha)
    return img

async def download_img(url, size=None):
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content)).convert("RGBA")
                if size: img = img.resize(size)
                return img
        except:
            pass
    return None

# ---------- 主绘图 ----------
async def draw_malody_rank(chart_info: dict, mode_name: str, records: list) -> bytes:
    header_h = 500
    row_h = 160 
    width = 1920
    total_h = header_h + len(records) * row_h + 80
    
    # 基础画布颜色
    im = Image.new("RGBA", (width, total_h), (25, 30, 35, 255))

    # 【优化】玻璃背景效果：提高虚化背景的透明度可见性，让背景更清晰地透出
    cover = chart_info.get("cover_url", "")
    if cover:
        raw = await download_img(cover)
        if raw:
            bg = raw.resize((width, total_h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=60))
            bg.putalpha(160)  # 从 120 提高到 160，强化毛玻璃质感
            im.paste(bg, (0,0), bg)

    draw = ImageDraw.Draw(im)

    # 绘制封面与头部信息
    if cover:
        sc = await download_img(cover, (280, 280))
        if sc:
            im.alpha_composite(draw_fillet(sc, 20), (40, 40))

    title = chart_info.get("title", "")
    artist = chart_info.get("artist", "")
    if artist:
        title = f"{artist} - {title}"
    draw.text((360, 60), title, font=f_title, fill=(255, 255, 255))

    det = []
    if chart_info.get("level"): det.append(f"Lv.{chart_info['level']}")
    det.append(chart_info.get("mode_text", mode_name))
    if chart_info.get("creator"): det.append(f"by {chart_info['creator']}")
    draw.text((360, 155), " | ".join(det), font=f_info, fill=(220, 220, 220))

    il = []
    for k, l in [("sid","SID"),("cid","CID"),("length","Length"),("bpm","BPM")]:
        v = chart_info.get(k, "")
        if v: il.append(f"{l}: {v}")
    draw.text((360, 220), "  ".join(il), font=f_info, fill=(180, 180, 180))


    draw.line([(30, header_h-65), (width-30, header_h-65)], fill=(255,255,255,80), width=2)

    # 【优化】基于 1920 宽度科学重构列坐标，完美防拥挤
    # 各列: 排名, 玩家, 分数, Acc, Combo, Best判定, FC, Mod, Time
    cols = [50, 130, 520, 740, 960, 1120, 1370, 1430, 1640]  
    heads = ["#", "Player", "Score", "Acc%", "Combo", "Best/C/G/M", "FC", "Mod", "Time"]
    
    for i, h in enumerate(heads):
        hx = cols[i]
        if i == 1: hx += 120  # 对齐头像右侧昵称
        draw.text((hx, header_h - 45), h, font=f_head, fill=(255, 210, 120), anchor="lm")

    # 并发预加载资产
    avatars = [download_img(r.get("avatar_url"), (100, 100)) for r in records]
    all_mods = {c for r in records for c in r.get("mod_icons", [])}
    await asyncio.gather(*[download_mod_icon(c) for c in all_mods])
    avas = await asyncio.gather(*avatars)

    # ---------- 在右上角绘制第一名头像（大图方形圆角，与封面同尺寸）----------
    if records and records[0].get("avatar_url"):
        # 单独下载第一名头像的原图（不预先缩放到100x100，获取原始尺寸）
        top_avatar_full = await download_img(records[0]["avatar_url"], (280, 280))
        if top_avatar_full:
            # 使用与封面相同的圆角处理（半径20px）
            avatar_rounded = draw_fillet(top_avatar_full, 20)
            # 位置：右边缘留40px，上边缘留40px
            x = width - 40 - 280
            y = 40
            im.alpha_composite(avatar_rounded, (x, y))
            
            # 可选：添加金色边框（与之前保持一致）
            draw.rectangle([x, y, x+280, y+280], outline=(255, 215, 0, 255), width=5)
            # 添加 “#1” 标签，位置在大图下方中央
            draw.text((x+140, y+290), "#1", font=f_sml, fill=(255, 215, 0), anchor="mt")

    # 绘制每一行
    for i, rec in enumerate(records):
        y = header_h + i * row_h
        
        # 【优化】透明度极低化，打造高级通透玻璃观感 (70 和 40)
        bg_c = (45, 55, 60, 70) if i % 2 == 0 else (30, 40, 45, 40)
        draw.rectangle([15, y, width-15, y+row_h-5], fill=bg_c)
        ty = y + (row_h-5)//2 + 4

        # 1. 排名
        draw.text((cols[0], ty), str(rec.get("ranking", i+1)), font=f_row, fill=(255,255,255), anchor="lm")

        # 2. 头像与昵称
        av = avas[i] if i < len(avas) else None
        if av:
            im.alpha_composite(draw_fillet(av, 12), (cols[1], y+(row_h-100)//2))
        name = rec.get("username", "?")
        if len(name) > 9: name = name[:8] + "…"
        draw.text((cols[1]+120, ty), name, font=f_row, fill=(255,255,255), anchor="lm")

        # 3. 分数
        draw.text((cols[2], ty), f"{rec.get('score', 0):,}", font=f_row, fill=(255,255,255), anchor="lm")

        # 4. Acc 彩色进度条
        acc = rec.get("acc", 0)
        color = get_acc_color(rec.get("acc_color", ""))
        bar_w, bar_h = 180, 44
        bx, by = cols[3], ty - bar_h//2
        draw.rounded_rectangle([bx, by, bx+bar_w, by+bar_h], radius=10, fill=(30, 30, 30, 160))
        fw = int(bar_w * min(acc, 100) / 100)
        if fw > 0: 
            draw.rounded_rectangle([bx, by, bx+fw, by+bar_h], radius=10, fill=color)
        
        draw.text((bx+bar_w/2+2, by+bar_h/2+2), f"{acc:.2f}%", font=f_acc, fill=(0,0,0,160), anchor="mm")
        draw.text((bx+bar_w/2, by+bar_h/2), f"{acc:.2f}%", font=f_acc, fill=(255,255,255), anchor="mm")

        # 5. Combo
        draw.text((cols[4], ty), f"{rec.get('combo', 0)}x", font=f_row, fill=(255,255,100), anchor="lm")

        # 6. Best/C/G/M
        best = rec.get("best")
        judge = f"{best}/{rec.get('cool',0)}/{rec.get('good',0)}/{rec.get('miss',0)}" if best is not None else "-"
        draw.text((cols[5], ty), judge, font=f_sml, fill=(220,220,220), anchor="lm")

        # 7. FC 圆点
        fc = rec.get("fc")
        if fc is not None:
            cc = (0, 230, 100) if fc else (230, 50, 50)
            draw.ellipse((cols[6], ty-15, cols[6]+30, ty+15), fill=cc)

        # 8. Mod 图标
        mods = rec.get("mod_icons", [])
        if mods:
            mx = cols[7]
            for cls in mods:
                icon = _mod_cache.get(cls)
                if icon:
                    im.alpha_composite(icon, (mx, ty-32))
                    mx += 64 + 6
        else:
            draw.text((cols[7], ty), "None", font=f_sml, fill=(180,180,180), anchor="lm")

        # 9. 【优化】游玩时间（双行智能拆分）
        time_str = rec.get("time", "")
        # 若包含空格（一般为日期和时间的分割线），则上下两行显示
        if " " in time_str:
            t1, t2 = time_str.split(" ", 1)
            draw.text((cols[8], ty - 20), t1, font=f_sml, fill=(200,200,200), anchor="lm")
            draw.text((cols[8], ty + 20), t2, font=f_sml, fill=(200,200,200), anchor="lm")
        else:
            draw.text((cols[8], ty), time_str, font=f_sml, fill=(200,200,200), anchor="lm")

    buf = BytesIO()
    im.convert("RGBA").save(buf, "PNG", quality=100) # 画质稍微提升到了 95，防止模糊渐变产生色带
    return buf.getvalue()