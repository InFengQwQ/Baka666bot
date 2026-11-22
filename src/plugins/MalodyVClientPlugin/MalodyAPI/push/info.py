"""系统信息/推送信息 API"""
from ..core import _get


def get_system_info(
    access_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _get("push/info/wt", {}, access_token=access_token, uid=uid, timeout=timeout)
