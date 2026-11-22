"""检查皮肤 API"""
from ..core import _get


def check_skin(
    store_token: str,
    uid: str,
    skin_hash: str,
    timeout: int = 10,
) -> dict:
    params = {"hash": skin_hash}
    return _get("skin/check", params, access_token=store_token, uid=uid, use_store=True)
