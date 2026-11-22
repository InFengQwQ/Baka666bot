"""禁言/屏蔽 API"""
from ..core import _post


def set_mute(
    access_token: str,
    uid: str,
    target_uid: str,
    mute: bool = True,
    timeout: int = 10,
) -> dict:
    data = {"touid": target_uid, "mute": "1" if mute else "0"}
    return _post("player/mute", data, access_token=access_token, uid=uid, timeout=timeout)
