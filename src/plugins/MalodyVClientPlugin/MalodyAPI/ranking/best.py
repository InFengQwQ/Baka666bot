"""Malody API: ranking/best - 获取玩家最佳成绩"""
from ..core import _get


def get_best(access_token: str, uid: str, touid: str, mode: str = "0", from_: int = 0, limit: int = None, timeout: int = None) -> dict:
    params = {"touid": touid, "mode": mode, "from": from_}
    if limit is not None:
        params["limit"] = limit
    return _get("ranking/best", params, access_token=access_token, uid=uid, timeout=timeout)