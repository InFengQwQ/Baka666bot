"""点赞谱面 API"""
from ...core import _post


def like_chart(
    access_token: str,
    uid: str,
    cid: str,
    like: bool = True,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "like": "1" if like else "0"}
    return _post("community/chart/like", data, access_token=access_token, uid=uid, timeout=timeout)
