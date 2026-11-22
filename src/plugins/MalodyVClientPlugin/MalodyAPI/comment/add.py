"""添加评论 API"""
from ..core import _post


def add_comment(
    access_token: str,
    uid: str,
    cid: str,
    content: str,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "content": content}
    return _post("comment/add", data, access_token=access_token, uid=uid, timeout=timeout)
