"""删除审核 API"""
from ..core import _post


def delete_review(
    access_token: str,
    uid: str,
    review_id: str,
    timeout: int = 10,
) -> dict:
    data = {"id": review_id}
    return _post("review/delete", data, access_token=access_token, uid=uid, timeout=timeout)
