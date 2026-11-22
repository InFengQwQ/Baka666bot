"""任务列表 API"""
from ..core import _get


def get_quest(
    access_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _get("quest/list", {}, access_token=access_token, uid=uid)
