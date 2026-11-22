"""皮肤上传签名 API"""
from ...core import _post


def get_skin_upload_sign(
    store_token: str,
    uid: str,
    filename: str,
    filesize: int,
    filehash: str,
    timeout: int = 10,
) -> dict:
    data = {"name": filename, "size": str(filesize), "hash": filehash}
    return _post("skin/upload/sign", data, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
