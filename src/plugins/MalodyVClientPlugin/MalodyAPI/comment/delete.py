"""删除评论 API"""
from ..core import _post


def delete_comment(
    access_token: str,
    uid: str,
    tid: str,
    timeout: int = 10,
) -> dict:
    data = {"tid": tid}
    return _post("comment/delete", data, access_token=access_token, uid=uid, timeout=timeout)
