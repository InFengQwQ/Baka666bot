"""成就列表 API"""
from ...core import _get


def get_achieve(
    access_token: str,
    uid: str,
    touid: str = None,
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid}
    return _get("achieve/player/all", params, access_token=access_token, uid=uid)
