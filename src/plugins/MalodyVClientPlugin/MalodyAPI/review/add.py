"""添加审核 API"""
from ..core import _post


def add_review(
    access_token: str,
    uid: str,
    cid: str,
    content: str,
    type_: str = "0",
    audio_time: int = 0,
    timeout: int = 10,
) -> dict:
    data = {"cid": cid, "content": content, "type": type_, "audio": str(audio_time)}
    return _post("review/add", data, access_token=access_token, uid=uid, timeout=timeout)
