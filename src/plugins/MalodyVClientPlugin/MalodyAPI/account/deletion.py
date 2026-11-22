"""注销账号 API"""
from ..core import _post


def delete_account(
    access_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _post("account/deletion", {}, access_token=access_token, uid=uid, timeout=timeout)
