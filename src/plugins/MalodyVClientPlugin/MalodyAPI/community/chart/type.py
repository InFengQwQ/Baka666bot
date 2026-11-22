"""设置谱面类型 API"""
from ...core import _post


def set_chart_type(
    access_token: str,
    uid: str,
    cid: str,
    type_: str,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "type": type_}
    return _post("community/chart/type", data, access_token=access_token, uid=uid, timeout=timeout)
