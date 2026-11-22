"""玩家头像上传 API"""
from ..core import API_BASE, HEADERS, DEFAULT_TIMEOUT


def upload_avatar(image_data: bytes, filename: str, access_token: str, uid: str, timeout: int = None) -> dict:
    import requests, time
    timeout = timeout or DEFAULT_TIMEOUT
    url = f"{API_BASE}/api/player/image"
    params = {"key": access_token, "uid": uid, "t": int(time.time())}
    files = {"file": (filename, image_data, "image/png")}
    resp = requests.post(url, params=params, files=files, headers=HEADERS, verify=False, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Avatar upload failed: {data}")
    return data
