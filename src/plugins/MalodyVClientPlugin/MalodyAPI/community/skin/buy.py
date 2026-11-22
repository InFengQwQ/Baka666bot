"""社区皮肤购买（公开） API"""
from ...core import _post


def buy_skin_pub(
    access_token: str,
    uid: str,
    skin_id: str,
    timeout: int = 10,
) -> dict:
    data = {"id": skin_id}
    return _post("community/skin/buy", data, access_token=access_token, uid=uid, timeout=timeout)
