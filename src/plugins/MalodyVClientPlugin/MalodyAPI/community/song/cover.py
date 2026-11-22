"""歌曲封面上传 API"""
from ...core import API_BASE, HEADERS, DEFAULT_TIMEOUT


def upload_song_cover(access_token: str, uid: str, sid: str, image_data: bytes, filename: str = "cover.png", timeout: int = None) -> dict:
    import requests, time
    timeout = timeout or DEFAULT_TIMEOUT
    url = f"{API_BASE}/api/community/song/cover"
    params = {"key": access_token, "uid": uid, "sid": sid, "t": int(time.time())}
    files = {"file": (filename, image_data, "image/png")}
    resp = requests.post(url, params=params, files=files, headers=HEADERS, verify=False, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Cover upload failed: {data}")
    return data
