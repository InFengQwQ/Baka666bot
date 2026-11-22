"""活动列表 API"""
from ..core import _get


def get_events(
    store_token: str,
    uid: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit}
    return _get("store/events", params, access_token=store_token, uid=uid, use_store=True)
