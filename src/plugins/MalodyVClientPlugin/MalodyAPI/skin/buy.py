"""购买皮肤 API"""
from ..core import _post


def buy_skin(
    store_token: str,
    uid: str,
    skin_id: str,
    timeout: int = 10,
) -> dict:
    data = {"id": skin_id}
    return _post("skin/buy", data, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
