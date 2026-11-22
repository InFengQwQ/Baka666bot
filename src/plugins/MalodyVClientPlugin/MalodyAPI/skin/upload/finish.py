"""完成皮肤上传 API"""
from ...core import _post


def upload_skin_finish(
    store_token: str,
    uid: str,
    skin_id: str,
    filename: str,
    filehash: str,
    timeout: int = 10,
) -> dict:
    data = {"id": skin_id, "name": filename, "hash": filehash}
    return _post("skin/upload/finish", data, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
