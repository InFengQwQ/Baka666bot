"""完成上传 API（商店）"""
from ...core import _post


def upload_finish(
    store_token: str,
    uid: str,
    filename: str,
    filehash: str,
    sid: str = "",
    timeout: int = 10,
) -> dict:
    data = {"name": filename, "hash": filehash, "sid": sid}
    return _post("store/upload/finish", data, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
