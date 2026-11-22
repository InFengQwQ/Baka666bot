"""添加/删除好友 API"""
from ...core import _post


def toggle_friend(
    access_token: str,
    uid: str,
    target_uid: str,
    add: bool = True,
    timeout: int = 10,
) -> dict:
    data = {"touid": target_uid}
    return _post("player/friend/toggle", data, access_token=access_token, uid=uid, timeout=timeout)
