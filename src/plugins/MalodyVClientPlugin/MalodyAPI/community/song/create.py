"""创建歌曲 API"""
from ...core import _post


def create_song(
    access_token: str,
    uid: str,
    title: str,
    artist: str,
    timeout: int = 10,
) -> dict:
    data = {"title": title, "artist": artist}
    return _post("community/song/create", data, access_token=access_token, uid=uid, timeout=timeout)
