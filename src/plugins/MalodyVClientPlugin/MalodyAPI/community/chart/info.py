"""谱面详情 API"""
from ...core import _get


def get_chart_info(
    access_token: str,
    uid: str,
    cid: str,
    timeout: int = 10,
) -> dict:
    params = {"cid": cid}
    return _get("community/chart/info", params, access_token=access_token, uid=uid)
