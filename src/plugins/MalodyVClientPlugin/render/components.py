"""渲染组件 — 参照 mmbest.py 视觉标准 (Torus 字体/圆角封面/模糊背景/暗色主题)"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import httpx, os
from pathlib import Path

from src.plugin_runtime import plugin_resource_dir
plugin_dir = plugin_resource_dir("nonebot_plugin_osubot")
font_dir = plugin_dir / "osufile" / "fonts"

def _font(size: int):
    if font_dir.exists():
        try: return ImageFont.truetype(str(font_dir / "Torus Regular.otf"), size)
        except: pass
        try: return ImageFont.truetype(str(font_dir / "Torus SemiBold.otf"), size)
        except: pass
    for name in ("msyh.ttc", "simhei.ttf"):
        try: return ImageFont.truetype(name, size)
        except: pass
    return ImageFont.load_default()

F = {s: _font(s) for s in (10,11,12,13,14,15,16,18,20,22,24,28)}
BG = (31, 41, 46)
ACCENT = (238, 171, 0)
TEXT = (220, 220, 220)
DIM = (140, 140, 140)
PINK = (255, 102, 171)
LINK = (102, 204, 255)

async def _fetch(url: str, size=None) -> Image.Image | None:
    try:
        async with httpx.AsyncClient(verify=False, timeout=5) as c:
            r = await c.get(url)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            return img.resize(size) if size else img
    except: pass
    return None

def _round(img: Image.Image, r: int) -> Image.Image:
    w, h = img.size
    circle = Image.new("L", (r*2, r*2), 0)
    ImageDraw.Draw(circle).ellipse((0, 0, r*2, r*2), fill=255)
    a = Image.new("L", (w, h), 255)
    a.paste(circle.crop((0,0,r,r)), (0,0)); a.paste(circle.crop((r,0,r*2,r)), (w-r,0))
    a.paste(circle.crop((r,r,r*2,r*2)), (w-r,h-r)); a.paste(circle.crop((0,r,r,r*2)), (0,h-r))
    img = img.convert("RGBA"); img.putalpha(a); return img

def _blur_bg(img: Image.Image, size: tuple, r: int) -> Image.Image:
    bg = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.5)
    bg = bg.filter(ImageFilter.BoxBlur(radius=2))
    return _round(bg, r)


async def chart_card(cid: str, title: str, version: str, artist: str = "", creator: str = "",
                     sid: str = "", mode: str = "", length: str = "", like: str = "",
                     cover_url: str = None, width: int = 700) -> bytes:
    h = 180; im = Image.new("RGBA", (width, h), BG); draw = ImageDraw.Draw(im)
    if cover_url:
        cv = await _fetch(cover_url)
        if cv:
            blur = _blur_bg(cv, (width-40, h-20), 15); im.paste(blur, (20, 10), blur)
            cv_sq = ImageOps.fit(cv, (150, 150), Image.Resampling.LANCZOS)
            im.paste(_round(cv_sq, 15), (16, 15), _round(cv_sq, 15))
    x = 180
    draw.text((x, 20), title[:32], font=F[22], fill=ACCENT)
    if artist: draw.text((x, 52), f"by {artist[:28]}", font=F[14], fill=DIM)
    rows = [("CID",cid),("SID",sid),("难度",version[:28]),("作者",creator[:22]),
            ("模式",mode),("时长",f"{length}s"),("点赞",like)]
    y = 82
    for label, val in rows:
        if val:
            draw.text((x, y), f"{label}:", font=F[13], fill=DIM)
            draw.text((x+54, y), val[:32], font=F[14], fill=TEXT)
            y += 22
    bio = BytesIO(); im.convert("RGB").save(bio, "PNG"); return bio.getvalue()


async def profile_card(username: str, uid: str, avatar_hash: str = "", gold: str = "",
                       playtime: str = "", played: str = "", gender: str = "",
                       rank_rows: list = None, width: int = 700) -> bytes:
    h = 130 + (len(rank_rows or []) * 24) + 30
    im = Image.new("RGBA", (width, max(h,200)), BG); draw = ImageDraw.Draw(im)
    if avatar_hash:
        av = await _fetch(f"https://cni.machart.top/avatar/{avatar_hash}", (80,80))
        if av: im.paste(_round(av, 40), (20, 20), _round(av, 40))
    x = 115
    draw.text((x, 18), username[:24], font=F[22], fill=ACCENT)
    draw.text((x, 48), f"UID: {uid}  |  Gold: {gold}  |  {gender}", font=F[13], fill=DIM)
    draw.text((x, 74), f"注册: {playtime}  总游玩: {played}", font=F[13], fill=DIM)
    y = 115
    if rank_rows:
        f_div = Image.new("RGBA", (width-30, 1), (255,255,255,40)); im.paste(f_div, (15,y), f_div); y += 10
        for mn, rank, lv, pc, acc, combo in rank_rows:
            draw.text((16, y), f"  [{mn}] Rank:{rank}  Lv.{lv}  PC:{pc}  Acc:{acc}%  Combo:{combo}", font=F[13], fill=TEXT)
            y += 24
    bio = BytesIO(); im.convert("RGB").save(bio, "PNG"); return bio.getvalue()


async def list_view(title: str, items: list, page_info: str = "", width: int = 700) -> bytes:
    per_page = min(len(items), 10); line_h = 30
    h = 30 + per_page * line_h + 50
    im = Image.new("RGBA", (width, h), BG); draw = ImageDraw.Draw(im)
    draw.text((16, 10), title, font=F[20], fill=ACCENT)
    y = 42
    for idx, item in enumerate(items[:per_page]):
        draw.text((12, y+2), str(idx+1), font=F[12], fill=DIM)
        x = 32
        for key, val in item.items():
            s = str(val)[:30]; c = PINK if (key=="rank" and idx<3) else TEXT
            draw.text((x, y+2), s, font=F[13], fill=c); x += 145
        y += line_h
    if page_info: draw.text((16, y+8), page_info, font=F[12], fill=DIM)
    bio = BytesIO(); im.convert("RGB").save(bio, "PNG"); return bio.getvalue()


async def simple_rows(title: str, rows: list[tuple], width: int = 600) -> bytes:
    h = 30 + len(rows)*24 + 30
    im = Image.new("RGBA", (width, h), BG); draw = ImageDraw.Draw(im)
    draw.text((16, 10), title, font=F[18], fill=ACCENT)
    y = 44
    for label, val in rows:
        draw.text((16, y), label, font=F[13], fill=DIM)
        if val:
            tw = draw.textlength(label, F[13]); draw.text((16+tw+8, y), str(val)[:60], font=F[14], fill=TEXT)
        y += 24
    bio = BytesIO(); im.convert("RGB").save(bio, "PNG"); return bio.getvalue()

simple_list = list_view
simple_card = simple_rows
