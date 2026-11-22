"""消息推送 API"""
from ..core import _get


def get_messages(
    access_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _get("push/message", {}, access_token=access_token, uid=uid)
