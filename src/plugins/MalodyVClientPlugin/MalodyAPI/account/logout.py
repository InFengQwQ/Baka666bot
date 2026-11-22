"""登出 API"""
from ..core import _post


def malody_logout(
    access_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _post("account/logout", {}, access_token=access_token, uid=uid, timeout=timeout)
