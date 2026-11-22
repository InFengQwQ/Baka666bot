"""商店谱面列表 API"""
from ..core import _get


def get_store_charts(
    store_token: str,
    uid: str,
    sid: str,
    from_: int = 0,
    limit: int = 20,
    mode: str = "0",
    timeout: int = 10,
) -> dict:
    params = {"sid": sid, "from": from_, "limit": limit, "mode": mode}
    return _get("store/charts", params, access_token=store_token, uid=uid, use_store=True)
