"""商店列表 API"""
from ..core import _get


def get_store_list(
    store_token: str,
    uid: str,
    from_: int = 0,
    limit: int = 20,
    mode: str = "0",
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit, "mode": mode}
    return _get("store/list", params, access_token=store_token, uid=uid, use_store=True)
