"""审核状态变更 API"""
from ..core import _post


def change_review(
    access_token: str,
    uid: str,
    review_id: str,
    status: str,
    timeout: int = 10,
) -> dict:
    data = {"id": review_id, "status": status}
    return _post("review/status", data, access_token=access_token, uid=uid, timeout=timeout)
