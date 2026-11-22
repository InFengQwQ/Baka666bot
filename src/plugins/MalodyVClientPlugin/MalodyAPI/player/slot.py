"""玩家 Slot 数据 API"""
from ..core import _post


def set_chart_slot(
    access_token: str,
    uid: str,
    mode: str,
    slots: list,
    timeout: int = 10,
) -> dict:
    data = {"mode": mode, "slots": ",".join(str(s) for s in slots)}
    return _post("player/slot", data, access_token=access_token, uid=uid, timeout=timeout)
