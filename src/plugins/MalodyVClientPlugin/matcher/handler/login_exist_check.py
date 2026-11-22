# matcher/handler/login_exist_check.py

async def check_username_exists(username: str) -> bool:
    """占位：检查用户名是否存在，目前一律返回 True"""
    return True

async def get_username_by_uid(uid: int) -> str:
    """占位：通过 UID 获取用户名，目前返回空字符串"""
    return ""

async def get_uid_by_username(keyword: str) -> str | None:
    """占位：根据关键词返回 UID，目前仅支持纯数字"""
    if keyword.isdigit():
        return keyword
    return None

async def get_user_profile(uid: str, mode: str):
    """占位：返回用户资料 (user_name, avatar_url, rank_text, mode_stats)"""
    return None, None, None, None