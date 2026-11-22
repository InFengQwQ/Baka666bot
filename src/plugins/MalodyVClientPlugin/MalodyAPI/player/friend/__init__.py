"""好友 API"""
from ...core import _get


def get_friend_list(access_token: str, uid: str, from_: int = 0, limit: int = 50, timeout: int = None) -> dict:
    params = {"from": from_, "limit": limit}
    return _get("player/friend", params, access_token=access_token, uid=uid, timeout=timeout)
