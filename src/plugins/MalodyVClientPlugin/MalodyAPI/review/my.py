"""我的审核 API"""
from ..core import _get


def get_my_review(
    access_token: str,
    uid: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit}
    return _get("review/my", params, access_token=access_token, uid=uid)
