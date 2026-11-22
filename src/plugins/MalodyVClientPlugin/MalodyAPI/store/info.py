"""商店详情 API"""
from ..core import _get


def get_store_info(
    store_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _get("store/info", {}, access_token=store_token, uid=uid, use_store=True)
