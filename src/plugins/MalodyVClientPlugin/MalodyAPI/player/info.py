"""玩家信息 API"""
from ..core import _get


def get_player_info(touid: str, access_token: str, uid: str, timeout: int = None) -> dict:
    params = {"touid": touid}
    return _get("player/info", params, access_token=access_token, uid=uid, timeout=timeout)