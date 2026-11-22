"""全球排名 API"""
from ..core import _get


def get_global_rank(
    access_token: str,
    uid: str,
    mode: str = "0",
    type_: str = "pc",
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"mode": mode, "type": type_, "from": from_, "limit": limit}
    return _get("ranking/global", params, access_token=access_token, uid=uid)
