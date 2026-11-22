"""成绩记录/放弃提交 API"""
from ...core import _post


def submit_score_abort(
    access_token: str,
    uid: str,
    cid: str,
    mode: str = "0",
    timeout: int = 30,
) -> dict:
    data = {"cid": cid, "mode": mode}
    return _post("ranking/score/record", data, access_token=access_token, uid=uid, timeout=timeout)
