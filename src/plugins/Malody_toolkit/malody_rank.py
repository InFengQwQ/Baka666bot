from src.plugin_runtime import required_malody_account, malody_web_cookies
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment
from nonebot.params import CommandArg
from nonebot.adapters import Message
import time
import httpx
import re
from bs4 import BeautifulSoup
from nonebot.log import logger
from .malody_rank_draw import draw_malody_rank


rank_cmd = on_command("rank", priority=10, block=True)

async def fetch_chart_page(cid: int) -> dict:
    url = f"https://m.mugzone.net/chart/{cid}"
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": "; ".join(k + "=" + v for k, v in (await malody_web_cookies()).items())}
    result = {
        "cover_url": "", "title": "", "artist": "", "creator": "", "mode_text": "",
        "level": "", "sid": "", "length": "", "bpm": "", "web_records": []
    }
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return result
            soup = BeautifulSoup(resp.text, 'lxml')
            # cover
            og = soup.find('meta', property='og:image')
            if og and og.get('content'):
                result['cover_url'] = og['content']
            if not result['cover_url']:
                cover_div = soup.select_one('.coverb .cover')
                if cover_div and cover_div.get('style'):
                    m = re.search(r'url\(([^)]+)\)', cover_div.get('style'))
                    if m: result['cover_url'] = m.group(1).strip('"\'')
            if not result['cover_url']:
                result['cover_url'] = f"http://cni.machart.top/cover/{cid}!small"

            title_h2 = soup.find('h2', class_='title')
            if title_h2:
                for em in title_h2.find_all('em'): em.decompose()
                artist_span = title_h2.find('span', class_='artist')
                if artist_span:
                    result['artist'] = artist_span.get_text(strip=True)
                    artist_span.decompose()
                result['title'] = title_h2.get_text(strip=True).strip('- ')

            mode_h2 = soup.find('h2', class_='mode')
            if mode_h2:
                img = mode_h2.find('img')
                if img: result['mode_img'] = img.get('src', '')
                span = mode_h2.find('span')
                if span: result['mode_text'] = span.get_text(strip=True)
                a = mode_h2.find('a')
                if a: result['creator'] = a.get_text(strip=True)

            sub = soup.find('h2', class_='sub')
            if sub:
                for lab in sub.find_all('label'):
                    t = lab.get_text(strip=True)
                    ns = lab.find_next_sibling('span')
                    if 'ID' in t and ns: result['sid'] = ns.get_text(strip=True)
                    elif '长度' in t and ns: result['length'] = ns.get_text(strip=True)
                    elif 'BPM' in t and ns: result['bpm'] = ns.get_text(strip=True)

            ul = soup.select_one('ul.list')
            if ul:
                for li in ul.find_all('li'):
                    rec = {}
                    ttl = li.get('title', '')
                    if ttl:
                        parts = ttl.split('/')
                        if len(parts) == 4:
                            rec['best'], rec['cool'], rec['good'], rec['miss'] = parts
                    rank_img = li.select_one('span.rank img')
                    rec['avatar_url'] = rank_img.get('src', '') if rank_img else ''
                    name_a = li.select_one('span.name a')
                    if name_a:
                        rec['username'] = name_a.get_text(strip=True)
                        m = re.search(r'/user/(\d+)', name_a.get('href', ''))
                        rec['uid'] = m.group(1) if m else ''
                    else:
                        rec['username'] = 'Unknown'
                    score_s = li.select_one('span.score')
                    rec['score'] = score_s.get_text(strip=True) if score_s else '0'
                    combo_s = li.select_one('span.combo')
                    rec['combo'] = combo_s.get_text(strip=True) if combo_s else '0'
                    acc_span = li.select_one('span.acc')
                    if acc_span:
                        i = acc_span.find('i')
                        if i:
                            cls = i.get('class', [])
                            rec['acc_color'] = next((c for c in cls if c.startswith('color-')), '')
                        em = acc_span.find('em')
                        rec['acc'] = em.get_text(strip=True).replace('%', '') if em else '0'
                    else:
                        rec['acc'] = '0'; rec['acc_color'] = ''
                    mod_span = li.select_one('span.mod')
                    mod_icons = []
                    if mod_span:
                        for ic in mod_span.find_all('i'):
                            for c in ic.get('class', []):
                                if c.startswith('g_mod_'): mod_icons.append(c)
                    rec['mod_icons'] = mod_icons
                    time_span = li.select_one('span.time')
                    rec['time'] = time_span.get_text(strip=True) if time_span else ''
                    result['web_records'].append(rec)
    except Exception as e:
        logger.error(f"网页解析错误: {e}")
    return result

async def fetch_chart_ranking(cid: int, mode: int = 0):
    url = "https://api.mugzone.net/api/ranking/list"
    account_uid, account_key = await required_malody_account()
    params = {"key": account_key, "uid": account_uid, "cid": cid, "mode": mode, "from": 0, "t": int(time.time())}
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(url, params=params, headers={"User-Agent": "Malody 6.6.43"}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0: return data["data"]
    return None

@rank_cmd.handle()
async def handle_rank(bot: Bot, event: Event, args: Message = CommandArg()):
    plain = args.extract_plain_text().strip().split()
    if not plain:
        await rank_cmd.finish("格式：/rank c<cid> [mode(0-7)]")
        return
    cid_str = plain[0][1:] if plain[0].lower().startswith('c') else plain[0]
    if not cid_str.isdigit():
        await rank_cmd.finish("请输入有效谱面ID")
        return
    cid = int(cid_str)
    mode = plain[1] if len(plain) > 1 and plain[1].isdigit() and len(plain[1]) == 1 else "0"
    mode_name = {"0":"Key","1":"Step","2":"DJ","3":"Catch","4":"Pad","5":"Taiko","6":"Ring","7":"Slide"}.get(mode, f"Mode {mode}")

    page = await fetch_chart_page(cid)
    api = await fetch_chart_ranking(cid, int(mode))
    if not page['web_records'] and not api:
        await rank_cmd.finish("无数据")
        return

    merged, api_map = [], {}
    if api:
        for r in api: api_map[r["ranking"]] = r
    for i, web in enumerate(page['web_records']):
        rank = i + 1
        api_r = api_map.get(rank)
        if api_r:
            merged.append({
                "uid": api_r.get("uid", web.get("uid","")),
                "username": api_r.get("username", web.get("username")),
                "avatar_url": web.get("avatar_url") or f"https://cni.machart.top/avatar/{api_r.get('uid')}!avatar",
                "score": api_r.get("score",0), "acc": api_r.get("acc",0), "combo": api_r.get("combo",0),
                "best": api_r.get("best"), "cool": api_r.get("cool"), "good": api_r.get("good"), "miss": api_r.get("miss"),
                "fc": api_r.get("fc",False),
                "mod_icons": web.get("mod_icons",[]),
                "time": web.get("time",""),
                "acc_color": web.get("acc_color",""),
                "ranking": rank
            })
        else:
            merged.append({
                "uid": web.get("uid",""), "username": web.get("username","?"),
                "avatar_url": web.get("avatar_url",""),
                "score": int(web.get("score","0").replace(',','')) if web.get("score") else 0,
                "acc": float(web.get("acc","0")), "combo": int(web.get("combo","0")),
                "best": None, "cool": None, "good": None, "miss": None, "fc": None,
                "mod_icons": web.get("mod_icons",[]),
                "time": web.get("time",""),
                "acc_color": web.get("acc_color",""),
                "ranking": rank
            })
    info = {
        "title": page.get("title",""), "artist": page.get("artist",""),
        "creator": page.get("creator",""), "mode_text": page.get("mode_text", mode_name),
        "level": page.get("level",""), "length": page.get("length",""), "bpm": page.get("bpm",""),
        "sid": page.get("sid",""), "cid": cid, "cover_url": page["cover_url"]
    }
    try:
        img = await draw_malody_rank(info, mode_name, merged)
        await rank_cmd.send(MessageSegment.image(img))
    except Exception as e:
        logger.error(f"绘图失败: {e}")
        await rank_cmd.finish("图片生成失败，检查后台日志。")
