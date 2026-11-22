"""排行榜列表 API"""
from ..core import _get


def get_ranking_list(
    access_token: str,
    uid: str,
    cid: str,
    mode: str = "0",
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"cid": cid, "mode": mode, "from": from_, "limit": limit}
    return _get("ranking/list", params, access_token=access_token, uid=uid)
