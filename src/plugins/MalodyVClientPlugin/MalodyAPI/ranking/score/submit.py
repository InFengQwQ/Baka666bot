"""提交成绩 API"""
from ...core import _post


def submit_score(
    access_token: str,
    uid: str,
    cid: str,
    mode: str,
    score: int,
    combo: int,
    cool: int,
    good: int,
    miss: int,
    mod: int = 0,
    best: int = 0,
    fc: bool = False,
    pro: bool = False,
    session: int = 0,
    timeout: int = 30,
) -> dict:
    data = {
        "cid": cid,
        "mode": mode,
        "score": str(score),
        "combo": str(combo),
        "cool": str(cool),
        "good": str(good),
        "miss": str(miss),
        "mod": str(mod),
        "best": str(best),
        "fc": "1" if fc else "0",
        "pro": "1" if pro else "0",
        "session": str(session),
    }
    return _post("ranking/score/submit", data, access_token=access_token, uid=uid, timeout=timeout)
