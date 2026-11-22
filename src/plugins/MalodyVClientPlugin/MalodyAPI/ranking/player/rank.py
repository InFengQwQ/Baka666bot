"""玩家段位 API"""
from ...core import _get


def get_player_rank(
    access_token: str,
    uid: str,
    touid: str = None,
    mode: str = "0",
    timeout: int = 10,
) -> dict:
    params = {"touid": touid or uid, "mode": mode}
    return _get("ranking/player/rank", params, access_token=access_token, uid=uid)
