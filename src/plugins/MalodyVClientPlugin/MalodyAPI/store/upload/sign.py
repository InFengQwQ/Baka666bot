"""上传签名 API（商店）"""
from ...core import _post


def get_upload_sign(
    store_token: str,
    uid: str,
    filename: str,
    filesize: int,
    filehash: str,
    chart_hash: str = "",
    timeout: int = 10,
) -> dict:
    data = {
        "name": filename,
        "size": str(filesize),
        "hash": filehash,
        "chart": chart_hash,
    }
    return _post("store/upload/sign", data, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
