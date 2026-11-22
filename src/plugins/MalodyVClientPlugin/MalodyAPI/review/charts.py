"""审核谱面列表 API"""
from ..core import _get


def get_review_charts(
    access_token: str,
    uid: str,
    sid: str,
    timeout: int = 10,
) -> dict:
    params = {"sid": sid}
    return _get("review/charts", params, access_token=access_token, uid=uid)
