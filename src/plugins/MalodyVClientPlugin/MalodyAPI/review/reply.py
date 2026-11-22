"""审核回复 API"""
from ..core import _get, _post


def get_review_reply(
    access_token: str,
    uid: str,
    issue_id: str,
    timeout: int = 10,
) -> dict:
    params = {"id": issue_id}
    return _get("review/reply", params, access_token=access_token, uid=uid)


def add_review_reply(
    access_token: str,
    uid: str,
    issue_id: str,
    content: str,
    timeout: int = 10,
) -> dict:
    data = {"id": issue_id, "content": content}
    return _post("review/reply", data, access_token=access_token, uid=uid, timeout=timeout)
