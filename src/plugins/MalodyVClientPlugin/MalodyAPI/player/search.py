"""玩家搜索 API"""
from ..core import _get


def search_player(keyword: str, access_token: str, uid: str, from_: int = 0, limit: int = 20, timeout: int = None) -> dict:
    params = {"keyword": keyword, "from": from_, "limit": limit}
    return _get("player/search", params, access_token=access_token, uid=uid, timeout=timeout)