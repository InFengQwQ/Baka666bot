"""推广谱面 API"""
from ...core import _post


def set_chart_promote(
    access_token: str,
    uid: str,
    cid: str,
    promote: bool = True,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "promote": "1" if promote else "0"}
    return _post("community/chart/promote", data, access_token=access_token, uid=uid, timeout=timeout)
