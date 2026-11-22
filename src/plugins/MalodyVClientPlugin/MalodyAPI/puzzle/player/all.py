"""拼图进度 API"""
from ...core import _get


def get_puzzle(
    access_token: str,
    uid: str,
    touid: str = None,
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid}
    return _get("puzzle/player/all", params, access_token=access_token, uid=uid)
