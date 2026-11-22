"""审核操作 API"""
from ..core import _post


def review_action(
    access_token: str,
    uid: str,
    chart_id: str,
    action: str,
    comment: str = "",
    timeout: int = 10,
) -> dict:
    data = {"chart": chart_id, "action": action, "comment": comment}
    return _post("review/action", data, access_token=access_token, uid=uid, timeout=timeout)
