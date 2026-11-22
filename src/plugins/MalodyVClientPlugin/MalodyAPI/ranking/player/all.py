"""玩家全模式排名 API"""
from ...core import _get


def get_ranking_player_all(touid: str, access_token: str, uid: str, timeout: int = None) -> dict:
    params = {"touid": touid}
    return _get("ranking/player/all", params, access_token=access_token, uid=uid, timeout=timeout)