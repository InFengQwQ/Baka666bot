"""推广列表 API"""
from ..core import _get


def get_promote(
    store_token: str,
    uid: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit}
    return _get("store/promote", params, access_token=store_token, uid=uid, use_store=True)
