"""玩家道具列表 API"""
from ..core import _get


def get_player_items(
    access_token: str,
    uid: str,
    touid: str = None,
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid}
    return _get("player/items", params, access_token=access_token, uid=uid)
