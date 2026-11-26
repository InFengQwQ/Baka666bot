import requests
from typing import List, Dict, Optional

def fetch_songs(
    lvmin: int,
    lvmax: int,
    target_count: int = 100,
    *,
    store_key: str,
    store_uid: str,
    mode: Optional[int] = None,
    type_str: str = "2",          # 原来固定为 "2"，现在可配置
    word: Optional[str] = None,
    bpmmin: Optional[int] = None,
    bpmmax: Optional[int] = None,
    lenmin: Optional[int] = None,
    lenmax: Optional[int] = None,
) -> List[Dict]:
    """
    从 Malody 商店 API 抓取谱面，支持全部可选过滤条件。
    """

    base_url = "https://api.mugzone.net/api/store/list2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "dnt": "1",
        "sec-ch-ua-mobile": "?0",
        "origin": "https://malody.mugzone.net",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://malody.mugzone.net/",
        "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en-GB;q=0.7,en;q=0.6",
        "priority": "u=1, i"
    }

    base_params = {
        "mcver": "1",
        "sort": "time",
        "order": "desc",
        "org": "1",
        "key": store_key,
        "uid": store_uid,
        "lvmin": lvmin,
        "lvmax": lvmax,
        "type": type_str,          # 如 "2" 或 "2,0"
    }
    # 动态添加可选参数
    if mode is not None:
        base_params["mode"] = mode
    if word:
        base_params["word"] = word
    if bpmmin is not None:
        base_params["bpmmin"] = bpmmin
    if bpmmax is not None:
        base_params["bpmmax"] = bpmmax
    if lenmin is not None:
        base_params["lenmin"] = lenmin
    if lenmax is not None:
        base_params["lenmax"] = lenmax

    songs = []
    current_from = 0
    with requests.Session() as session:
        session.headers.update(headers)
        while len(songs) < target_count:
            params = {**base_params, "from": current_from}
            resp = session.get(base_url, params=params)
            data = resp.json()
            if data.get("code") != 0:
                break
            chunk = data.get("data", [])
            songs.extend(chunk)
            if not chunk or not data.get("hasMore"):
                break
            current_from = data.get("next", current_from + len(chunk))
    return songs[:target_count]
