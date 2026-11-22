"""评论列表 API"""
from ..core import _get


def get_comment_list(
    access_token: str,
    uid: str,
    cid: str = None,
    sid: str = None,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"from": from_, "limit": limit}
    if cid:
        params["cid"] = cid
    if sid:
        params["sid"] = sid
    return _get("comment/list", params, access_token=access_token, uid=uid)
