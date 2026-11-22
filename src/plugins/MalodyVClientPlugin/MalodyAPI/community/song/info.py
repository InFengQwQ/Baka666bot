"""歌曲信息 API"""
from ...core import _get


def get_song_info(
    access_token: str,
    uid: str,
    sid: str,
    timeout: int = 10,
) -> dict:
    params = {"sid": sid}
    return _get("community/song/info", params, access_token=access_token, uid=uid)
