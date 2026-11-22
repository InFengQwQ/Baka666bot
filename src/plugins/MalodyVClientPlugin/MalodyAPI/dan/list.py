"""段位列表 API"""
from ..core import _get


def get_dan_list(
    access_token: str,
    uid: str,
    touid: str = None,
    mode: str = "0",
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid, "mode": mode, "from": from_, "limit": limit}
    return _get("dan/list", params, access_token=access_token, uid=uid)
