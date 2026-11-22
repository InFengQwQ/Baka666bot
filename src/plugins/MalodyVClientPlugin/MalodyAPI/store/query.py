"""商店查询 API"""
from ..core import _get


def query_store(
    store_token: str,
    uid: str,
    keyword: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"keyword": keyword, "from": from_, "limit": limit}
    return _get("store/query", params, access_token=store_token, uid=uid, use_store=True)
