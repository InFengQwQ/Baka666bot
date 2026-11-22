"""精选列表 API"""
from ..core import _get


def get_choice(
    store_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _get("store/choice", {}, access_token=store_token, uid=uid, use_store=True)
