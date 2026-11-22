"""所有段位 API"""
from ..core import _get


def get_all_dan(
    access_token: str,
    uid: str,
    mode: str = "0",
    timeout: int = 10,
) -> dict:
    params = {"mode": mode}
    return _get("dan/all", params, access_token=access_token, uid=uid)
