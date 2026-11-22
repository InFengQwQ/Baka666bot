"""刷新令牌 API"""
from ..core import _post


def renew_token(
    access_token: str,
    uid: str,
    store_token: str = None,
    timeout: int = 30,
) -> dict:
    data = {}
    return _post("account/renew", data, access_token=access_token, uid=uid, timeout=timeout)
