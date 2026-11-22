"""玩家动态 API"""
from ..core import _get


def get_player_activity(touid: str, access_token: str, uid: str, from_: int = 0, limit: int = 20, timeout: int = None) -> dict:
    params = {"touid": touid, "from": from_, "limit": limit}
    return _get("player/activity", params, access_token=access_token, uid=uid, timeout=timeout)