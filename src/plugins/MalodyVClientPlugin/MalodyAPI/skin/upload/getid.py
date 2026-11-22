"""获取皮肤上传 ID API"""
from ...core import _post


def get_skin_id(
    store_token: str,
    uid: str,
    timeout: int = 10,
) -> dict:
    return _post("skin/upload/getid", {}, access_token=store_token, uid=uid, use_store=True, timeout=timeout)
