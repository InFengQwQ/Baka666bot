"""好友商店 API"""
from ..core import _get


def get_friend_store(
    store_token: str,
    uid: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit}
    return _get("store/friend", params, access_token=store_token, uid=uid, use_store=True)
