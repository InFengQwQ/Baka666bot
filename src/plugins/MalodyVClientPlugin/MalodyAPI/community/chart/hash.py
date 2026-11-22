"""更新谱面哈希 API"""
from ...core import _post


def update_chart_hash(
    access_token: str,
    uid: str,
    cid: str,
    hash_: str,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "hash": hash_}
    return _post("community/chart/hash", data, access_token=access_token, uid=uid, timeout=timeout)
