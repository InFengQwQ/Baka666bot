"""Malody 登录 API"""
import hashlib
import time
import requests
from ..core import API_BASE, MALODY_VERSION, VER, HEADERS, DEFAULT_TIMEOUT


def malody_login(username: str, password: str, device_id: str, api_base: str = None, timeout: int = None) -> dict:
    api_base = api_base or API_BASE
    timeout = timeout or DEFAULT_TIMEOUT
    pwd_md5 = hashlib.md5(password.encode()).hexdigest().lower()
    combined = f"{username}+{pwd_md5}+{device_id}+time"
    h = 0
    for ch in combined:
        h = (ord(ch) + 131 * h) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    bver = h % 10000 if h >= 0 else -(abs(h) % 10000)
    params = {"t": int(time.time())}
    data = {"name": username, "psw": pwd_md5, "h": device_id, "bver": str(bver), "ver": str(VER)}
    resp = requests.post(
        f"{api_base}/api/account/login/wt",
        params=params, data=data, headers=HEADERS, verify=False, timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"Login failed: {result}")
    return result