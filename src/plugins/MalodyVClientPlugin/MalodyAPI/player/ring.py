"""Ring 模式数据 API"""
from ..core import _post, _get


def save_player_ring(
    access_token: str,
    uid: str,
    ring_data: int,
    timeout: int = 10,
) -> dict:
    data = {"ring": str(ring_data)}
    return _post("player/ring", data, access_token=access_token, uid=uid, timeout=timeout)
