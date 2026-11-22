"""用户凭证获取工具"""
from ...MalodyAPI.database import db


async def get_user_creds(qq: str):
    """获取绑定的用户凭证。返回 (uid, user_dict) 或 (None, None)。"""
    uid = await db.get_uid_by_qq(qq)
    if not uid:
        return None, None
    user = await db.get_user(uid)
    if not user or not user.get("access_token"):
        return None, None
    return uid, user
