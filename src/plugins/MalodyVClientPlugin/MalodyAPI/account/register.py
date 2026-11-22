"""账号注册 API"""
from ..core import _post


def malody_register(
    username: str,
    password: str,
    email: str,
    device_id: str,
    access_token: str = None,
    uid: str = None,
    timeout: int = 60,
) -> dict:
    import hashlib
    pwd_md5 = hashlib.md5(password.encode()).hexdigest().lower()
    combined = f"{username}+{pwd_md5}+{device_id}+time"
    h = 0
    for ch in combined:
        h = (ord(ch) + 131 * h) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    bver = h % 10000 if h >= 0 else -(abs(h) % 10000)
    data = {
        "name": username,
        "psw": pwd_md5,
        "h": device_id,
        "bver": str(bver),
        "email": email,
    }
    return _post("account/register/wt", data, access_token=access_token, uid=uid, timeout=timeout)
