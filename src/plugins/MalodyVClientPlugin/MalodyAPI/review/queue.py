"""审核队列 API"""
from ..core import _get


def get_review_queue(
    access_token: str,
    uid: str,
    mode: str = "0",
    timeout: int = 10,
) -> dict:
    params = {"mode": mode}
    return _get("review/queue", params, access_token=access_token, uid=uid)
