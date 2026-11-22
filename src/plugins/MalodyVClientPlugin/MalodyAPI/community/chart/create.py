"""创建谱面 API"""
from ...core import _post


def create_chart(
    access_token: str,
    uid: str,
    sid: str,
    version: str,
    mode: str,
    level: str,
    length: str = "0",
    type_: str = "0",
    timeout: int = 10,
) -> dict:
    data = {
        "sid": sid,
        "version": version,
        "mode": mode,
        "level": level,
        "length": length,
        "type": type_,
    }
    return _post("community/chart/create", data, access_token=access_token, uid=uid, timeout=timeout)
