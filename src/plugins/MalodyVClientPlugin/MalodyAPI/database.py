# API/database.py
import json
import time
import aiosqlite
from pathlib import Path
from src.storage import plugin_data

DB_PATH = plugin_data("MalodyVClientPlugin") / "user_data.db"

REQUIRED_COLUMNS = {
    "uid",
    "device_id",
    "store_token",
    "access_token",
    "refresh_token",
    "web_cookies",
    "last_login_time",
    "login_count",
    "username",
    "avatar",
    "gold",
    "tcp_server",
    "group_list",
    "is_login",
    "created_at",
    "updated_at",
    "extra",
    "qq"
}


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.conn: aiosqlite.Connection = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        # A clean installation has no developer database. Create an empty schema.
        numeric = {"last_login_time", "created_at", "updated_at", "gold", "login_count", "is_login"}
        columns = ["uid TEXT PRIMARY KEY"] + [
            f'"{name}" ' + ("REAL DEFAULT 0" if name in numeric else "TEXT")
            for name in sorted(REQUIRED_COLUMNS - {"uid"})
        ]
        await self.conn.execute("CREATE TABLE IF NOT EXISTS user_bind (" + ", ".join(columns) + ")")
        await self.conn.commit()
        cursor = await self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_bind'"
        )
        if not await cursor.fetchone():
            raise RuntimeError("表 user_bind 不存在，请执行 schema.sql 建表！")
        await cursor.close()

        cursor = await self.conn.execute("PRAGMA table_info(user_bind)")
        columns = {row[1] async for row in cursor}
        await cursor.close()
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"表缺少列: {missing}，请更新表结构。")

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def save_user(
        self,
        uid: str,
        device_id: str,
        store_token: str,
        access_token: str = None,
        refresh_token: str = None,
        web_cookies: str = None,
        username: str = None,
        avatar: str = None,
        gold: int = None,
        tcp_server: str = None,
        group_list: list = None,
        is_login: bool = None,
        **extra_fields,
    ):
        now = time.time()
        old_extra = await self._get_extra(uid)
        if old_extra:
            old_extra.update(extra_fields)
        else:
            old_extra = extra_fields
        extra_json = json.dumps(old_extra, ensure_ascii=False) if old_extra else None
        groups_str = json.dumps(group_list) if group_list else None

        await self.conn.execute(
            """
            INSERT INTO user_bind (
                uid, device_id, store_token, access_token, refresh_token,
                web_cookies, last_login_time, username, avatar,
                gold, tcp_server, group_list, is_login, extra, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                device_id = excluded.device_id,
                store_token = excluded.store_token,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                web_cookies = excluded.web_cookies,
                last_login_time = excluded.last_login_time,
                username = excluded.username,
                avatar = excluded.avatar,
                gold = excluded.gold,
                tcp_server = excluded.tcp_server,
                group_list = excluded.group_list,
                is_login = excluded.is_login,
                extra = excluded.extra,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                device_id,
                store_token,
                access_token,
                refresh_token,
                web_cookies,
                now,
                username,
                avatar,
                gold,
                tcp_server,
                groups_str,
                is_login,
                extra_json,
                now,
                now,
            ),
        )
        cursor = await self.conn.execute(
            "SELECT uid FROM user_bind WHERE uid = ?", (uid,)
        )
        exists = await cursor.fetchone()
        await cursor.close()
        if exists:
            await self.conn.execute(
                "UPDATE user_bind SET login_count = login_count + 1 WHERE uid = ?",
                (uid,),
            )
        else:
            await self.conn.execute(
                "UPDATE user_bind SET login_count = 1 WHERE uid = ?", (uid,)
            )
        await self.conn.commit()

    async def get_user(self, uid: str) -> dict:
        cursor = await self.conn.execute(
            "SELECT * FROM user_bind WHERE uid = ?", (uid,)
        )
        row = await cursor.fetchone()
        if not row:
            await cursor.close()
            return None
        columns = [desc[0] for desc in cursor.description]
        await cursor.close()
        data = dict(zip(columns, row))
        if data.get("extra"):
            data["extra"] = json.loads(data["extra"])
        else:
            data["extra"] = {}
        if data.get("group_list"):
            data["group_list"] = json.loads(data["group_list"])
        return data

    async def _get_extra(self, uid: str) -> dict:
        cursor = await self.conn.execute(
            "SELECT extra FROM user_bind WHERE uid = ?", (uid,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row and row[0]:
            return json.loads(row[0])
        return {}
    # 新增到 Database 类中
    async def bind_qq(self, uid: str, qq: str):
        """将 uid 与 qq 绑定，自动处理冲突"""
        # 1. 如果该 QQ 已绑定其他 uid，先解除旧绑定
        old_uid = await self.get_uid_by_qq(qq)
        if old_uid and old_uid != uid:
            await self.conn.execute("UPDATE user_bind SET qq = NULL WHERE uid = ?", (old_uid,))
        # 2. 如果该 uid 已绑定其他 QQ，覆盖
        await self.conn.execute("UPDATE user_bind SET qq = ? WHERE uid = ?", (qq, uid))
        await self.conn.commit()

    async def unbind_qq(self, uid: str):
        await self.conn.execute("UPDATE user_bind SET qq = NULL WHERE uid = ?", (uid,))
        await self.conn.commit()

    async def get_uid_by_qq(self, qq: str) -> str | None:
        cursor = await self.conn.execute("SELECT uid FROM user_bind WHERE qq = ?", (qq,))
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def get_qq_by_uid(self, uid: str) -> str | None:
        cursor = await self.conn.execute("SELECT qq FROM user_bind WHERE uid = ?", (uid,))
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None
    # 在 API/database.py 的 Database 类中添加

    async def bind_qq(self, uid: str, qq: str):
        """将 UID 与 QQ 号唯一绑定，自动处理冲突"""
        # 解除该 QQ 旧绑定
        old_uid = await self.get_uid_by_qq(qq)
        if old_uid and old_uid != uid:
            await self.conn.execute("UPDATE user_bind SET qq = NULL WHERE uid = ?", (old_uid,))
        # 解除该 uid 旧绑定（如果有）
        old_qq = await self.get_qq_by_uid(uid)
        if old_qq and old_qq != qq:
            await self.conn.execute("UPDATE user_bind SET qq = NULL WHERE uid = ?", (uid,))
        # 建立新绑定
        await self.conn.execute("UPDATE user_bind SET qq = ? WHERE uid = ?", (qq, uid))
        await self.conn.commit()

    async def get_uid_by_qq(self, qq: str) -> str | None:
        cursor = await self.conn.execute("SELECT uid FROM user_bind WHERE qq = ?", (qq,))
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def get_qq_by_uid(self, uid: str) -> str | None:
        cursor = await self.conn.execute("SELECT qq FROM user_bind WHERE uid = ?", (uid,))
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None


# 全局单例
db = Database()
