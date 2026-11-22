"""玩家资料图片渲染"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import httpx


def _get_font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype("msyh.ttc", size)
    except Exception:
        try:
            return ImageFont.truetype("simhei.ttf", size)
        except Exception:
            return ImageFont.load_default()


async def draw_profile(info: dict, rank_data: dict = None) -> bytes:
    username = info.get("username", "Unknown")
    uid = info.get("uid", "?")
    avatar_hash = info.get("avatar", "")
    gold = info.get("gold", 0)
    play_time = info.get("playTime", 0)
    played_time = info.get("playedTime", 0)
    area = info.get("area", 0)
    birth = info.get("birth", 0)
    gender = info.get("gender", 0)

    import datetime
    reg_str = datetime.datetime.fromtimestamp(play_time).strftime("%Y-%m-%d") if play_time else "?"
    birth_str = datetime.datetime.fromtimestamp(birth).strftime("%Y-%m-%d") if birth else "?"
    gender_str = {0: "保密", 1: "男", 2: "女"}.get(gender, "?")

    w, h = 600, 300 + (len(rank_data.get("data", [])) * 28 if rank_data else 0)
    im = Image.new("RGBA", (w, max(h, 320)), (31, 41, 46, 255))
    draw = ImageDraw.Draw(im)
    font = _get_font(18)
    font_bold = _get_font(20, True)
    font_title = _get_font(24, True)

    draw.text((20, 15), f"{username}", font=font_title, fill=(255, 255, 255))
    draw.text((20, 50), f"UID: {uid}  |  Gold: {gold}  |  {gender_str}", font=font, fill=(180, 180, 180))
    draw.text((20, 78), f"注册: {reg_str}  |  生日: {birth_str}", font=font, fill=(150, 150, 150))
    draw.text((20, 106), f"总游玩时间: {played_time}s  |  地区: {area}", font=font, fill=(150, 150, 150))

    # 头像
    if avatar_hash:
        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(f"https://cni.machart.top/avatar/{avatar_hash}", timeout=5)
                if resp.status_code == 200:
                    avatar = Image.open(BytesIO(resp.content)).convert("RGBA").resize((80, 80))
                    im.paste(avatar, (w - 100, 10), avatar)
        except Exception:
            pass

    y = 140
    if rank_data:
        data = rank_data.get("data", [])
        if data:
            draw.text((20, y), "段位信息:", font=font_bold, fill=(238, 171, 0))
            y += 30
            mode_names = ["Key", "Step", "DJ", "Catch", "Pad", "Taiko", "Ring", "Slide"]
            for item in data[:8]:
                mode_idx = item.get("mode", 0)
                mode_name = mode_names[mode_idx] if mode_idx < len(mode_names) else f"Mode{mode_idx}"
                rank = item.get("rank", "?")
                level = item.get("level", "?")
                pc = item.get("pc", 0)
                acc = item.get("acc", 0)
                combo = item.get("combo", 0)
                text = f"  [{mode_name}] Rank:{rank} Lv.{level}  PC:{pc}  Acc:{acc:.2f}%  Combo:{combo}"
                draw.text((20, y), text, font=font, fill=(200, 200, 200))
                y += 28

    bio = BytesIO()
    im.convert("RGB").save(bio, "PNG")
    return bio.getvalue()
