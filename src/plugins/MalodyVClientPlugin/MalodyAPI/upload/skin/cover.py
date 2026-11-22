"""皮肤封面上传 API"""
from ...core import API_BASE, STORE_API, HEADERS, DEFAULT_TIMEOUT


def upload_skin_cover(store_token: str, uid: str, skin_id: str, image_data: bytes, filename: str = "cover.png", timeout: int = None) -> dict:
    import requests, time
    timeout = timeout or DEFAULT_TIMEOUT
    url = f"{API_BASE}/api/upload/skin/cover"
    params = {"api": STORE_API, "uid": uid, "key": store_token, "id": skin_id, "t": int(time.time())}
    files = {"file": (filename, image_data, "image/png")}
    resp = requests.post(url, params=params, files=files, headers=HEADERS, verify=False, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Skin cover upload failed: {data}")
    return data
