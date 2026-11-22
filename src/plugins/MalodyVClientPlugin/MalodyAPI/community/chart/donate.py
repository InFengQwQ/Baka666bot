"""赞助谱面 API"""
from ...core import _post


def donate_chart(
    access_token: str,
    uid: str,
    cid: str,
    gold: int,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "gold": str(gold)}
    return _post("community/chart/donate", data, access_token=access_token, uid=uid, timeout=timeout)
