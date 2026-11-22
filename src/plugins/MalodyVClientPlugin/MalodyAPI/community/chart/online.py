"""在线谱面信息 API"""
from ...core import _get


def get_chart_online(
    access_token: str,
    uid: str,
    cid: str = None,
    hash_: str = None,
    timeout: int = 10,
) -> dict:
    params = {}
    if cid:
        params["cid"] = cid
    if hash_:
        params["hash"] = hash_
    return _get("community/chart/online", params, access_token=access_token, uid=uid)
