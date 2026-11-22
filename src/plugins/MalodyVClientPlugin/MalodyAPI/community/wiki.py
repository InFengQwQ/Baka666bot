"""社区 Wiki API"""
from ..core import _get, _post


def get_wiki(
    access_token: str,
    uid: str,
    sid: str = None,
    cid: str = None,
    timeout: int = 10,
) -> dict:
    params = {}
    if sid:
        params["sid"] = sid
    if cid:
        params["cid"] = cid
    return _get("community/wiki", params, access_token=access_token, uid=uid)


def save_wiki(
    access_token: str,
    uid: str,
    sid: str,
    cid: str = None,
    wiki: str = "",
    timeout: int = 10,
) -> dict:
    data = {"sid": sid, "wiki": wiki}
    if cid:
        data["cid"] = cid
    return _post("community/wiki", data, access_token=access_token, uid=uid, timeout=timeout)
