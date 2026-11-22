"""活动排名 API"""
from ..core import _get


def get_event_ranking(
    access_token: str,
    uid: str,
    eid: str,
    from_: int = 0,
    limit: int = 20,
    timeout: int = 10,
) -> dict:
    params = {"eid": eid, "from": from_, "limit": limit}
    return _get("ranking/event", params, access_token=access_token, uid=uid)
