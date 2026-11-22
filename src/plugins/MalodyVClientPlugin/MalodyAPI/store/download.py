"""下载谱面 API"""
from ..core import _get


def get_download(
    store_token: str,
    uid: str,
    cid: str,
    timeout: int = 10,
) -> dict:
    params = {"cid": cid}
    return _get("store/download", params, access_token=store_token, uid=uid, use_store=True)
