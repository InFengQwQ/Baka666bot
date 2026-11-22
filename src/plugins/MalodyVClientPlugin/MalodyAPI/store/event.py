"""单个活动 API"""
from ..core import _get


def get_event(
    store_token: str,
    uid: str,
    eid: str,
    timeout: int = 10,
) -> dict:
    params = {"eid": eid}
    return _get("store/event", params, access_token=store_token, uid=uid, use_store=True)
