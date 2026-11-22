"""Marlo 记录 API"""
from ..core import _get


def get_marlo_record(
    access_token: str,
    uid: str,
    touid: str = None,
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid}
    return _get("player/marlo", params, access_token=access_token, uid=uid)
