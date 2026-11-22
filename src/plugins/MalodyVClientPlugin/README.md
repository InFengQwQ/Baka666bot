# MalodyVClientPlugin

基于 Nonebot2 + NapCat 的 MalodyV QQ 机器人插件，可模拟 Malody 客户端的所有网络 API 行为。

## 功能概览

本插件已完整实现 MalodyV 客户端所用全部 HTTP API 的 Python 封装，并按 `matcher → handler → render` 三层架构提供 QQ 机器人指令。

---

## Bot 指令列表

除 `/login` 外，**所有 `ma` 子命令均需先登录**。

### 登录与账号
| 指令 | 说明 |
|------|------|
| `/login <用户名>` | 登录并绑定（需私聊发密码） |
| `ma logout` | 登出 |

### 玩家信息
| 指令 | 说明 |
|------|------|
| `ma profile [玩家]` | 玩家资料(图片) |
| `ma search <关键词>` | 搜索玩家 |
| `ma rank [玩家] [模式]` | 全模式段位 |
| `ma dan [玩家] [模式]` | 段位通过记录 |
| `ma danall [模式]` | 全段位列表 |
| `ma friend` | 好友列表 |
| `ma addfriend <UID>` | 添加好友 |
| `ma achieve [玩家]` | 成就列表 |
| `ma items [玩家]` | 道具列表 |
| `ma marlo [玩家]` | Marlo 记录 |
| `ma activity [玩家]` | 近期动态 |
| `ma puzzle [玩家]` | 拼图进度 |

### 排行与成绩
| 指令 | 说明 |
|------|------|
| `/mb [玩家] [模式] [范围]` | Best 成绩(图片) |
| `ma global [模式] [类型] [数量]` | 全球排名 |
| `ma chartrank <CID> [模式] [数量]` | 谱面排行榜 |
| `ma eventrank <EID> [数量]` | 活动排名 |

### 谱面与商店
| 指令 | 说明 |
|------|------|
| `ma store [模式] [数量]` | 谱面商店 |
| `ma choice [数量]` | 精选内容 |
| `ma promote [数量]` | 推广列表 |
| `ma chart <CID>` | 谱面信息(含封面) |
| `ma chartlist <SID> [模式]` | 歌曲谱面列表 |
| `ma chartonline <hash>` | 在线谱面 |
| `ma song <SID>` | 歌曲信息 |
| `ma wiki <SID> [CID]` | Wiki 查询 |
| `ma skin [模式] [数量]` | 皮肤列表 |

### 翻页/数量控制

列表类命令支持**自动翻页**，通过 API `hasMore`/`next` 循环请求：

- `ma store 100` — 自动获取最多 100 条
- `ma store 1-200` — 获取第 1 到第 200 条
- 默认 50 条，所有列表以图片形式返回

### 社区与互动
| 指令 | 说明 |
|------|------|
| `ma comment <CID> [数量]` | 评论列表 |
| `ma addcomment <CID> <内容>` | 发表评论 |
| `ma delcomment <TID>` | 删除评论 |
| `ma like <CID>` | 点赞谱面 |
| `ma review <CID> [数量]` | 审核记录 |
| `ma reviewqueue [模式] [数量]` | 审核队列 |
| `ma myreview [数量]` | 我的审核 |
| `ma reviewcharts <SID>` | 谱面审核列表 |
| `ma addreview <CID> <内容>` | 添加审核 |
| `ma reviewreply <id> [回复]` | 审核回复(查/发) |
| `ma reviewaction <id> <action>` | 审核操作 |
| `ma reviewstatus <id> <status>` | 审核状态变更 |
| `ma delreview <id>` | 删除审核 |

### 谱面管理 (写操作)
| 指令 | 说明 |
|------|------|
| `ma createchart <SID> <ver> <mode> <level>` | 创建谱面 |
| `ma createsong <标题> <艺术家>` | 创建歌曲 |
| `ma donate <CID> <金币>` | 赞助谱面 |
| `ma chartpromote <CID> confirm` | 推广谱面(二次确认) |
| `ma settype <CID> <类型>` | 设置谱面类型 |
| `ma updatehash <CID> <hash>` | 更新谱面哈希 |
| `ma mychart [玩家] [数量]` | 我的/玩家谱面 |

### 商店与搜索
| 指令 | 说明 |
|------|------|
| `ma searchstore <关键词>` | 商店搜索 |
| `ma friendstore [数量]` | 好友商店 |
| `ma download <CID>` | 获取下载链接 |
| `ma storeinfo` | 商店信息 |

### 账号与安全
| 指令 | 说明 |
|------|------|
| `ma renew` | 刷新令牌 |
| `ma delaccount confirm` | 注销账号(二次确认) |
| `ma mute <UID> confirm` | 屏蔽玩家(二次确认) |
| `ma buyskin <ID> confirm` | 购买皮肤(二次确认) |
| `ma slot <模式> <slots>` | 设置插槽 |
| `ma skincheck <hash>` | 检查皮肤 |

### 其他
| 指令 | 说明 |
|------|------|
| `ma quest` | 任务列表 |
| `ma news` | 系统消息+推送 |
| `ma help` | 帮助图片(缓存) |
| `/mb` `/mm` | Best/分数计算 |

### 翻页/数量控制

列表类命令支持**自动翻页**，通过 API `hasMore`/`next` 循环请求：
- `ma store 100` — 自动获取最多 100 条
- `ma store 1-200` — 获取第 1 到第 200 条
- 默认 50 条，所有列表以图片形式返回

---

## API 实现清单

所有 API 均位于 `MalodyAPI/` 目录，基于 `api.mugzone.net`。

### 账号 (account)

| API 路径 | 实现文件 | 方法 | 说明 |
|----------|---------|------|------|
| `account/login/wt` | `account/login.py` | POST | 登录，含 bver 计算 |
| `account/register/wt` | `account/register.py` | POST | 注册 |
| `account/renew` | `account/renew.py` | POST | 刷新令牌 |
| `account/logout` | `account/logout.py` | POST | 登出 |
| `account/deletion` | `account/deletion.py` | POST | 注销账号 |

### 玩家 (player)

| API 路径 | 实现文件 | 方法 | 说明 |
|----------|---------|------|------|
| `player/info` | `player/info.py` | GET | 玩家详细信息 |
| `player/info/simple` | `player/info_simple.py` | GET | 玩家简要信息 |
| `player/search` | `player/search.py` | GET | 搜索玩家 |
| `player/friend` | `player/friend.py` | GET | 好友列表 |
| `player/friend/toggle` | `player/friend/toggle.py` | POST | 添加/删除好友 |
| `player/items` | `player/items.py` | GET | 道具列表 |
| `player/marlo` | `player/marlo.py` | GET | Marlo 记录 |
| `player/mute` | `player/mute.py` | POST | 禁言/屏蔽 |
| `player/ring` | `player/ring.py` | POST | Ring 模式数据 |
| `player/slot` | `player/slot.py` | POST | 插槽数据 |
| `player/image` | `player/image.py` | POST | 上传头像 |
| `player/activity` | `player/avtivity.py` | GET | 玩家动态 |

### 排行 (ranking)

| API 路径 | 实现文件 | 方法 | 说明 |
|----------|---------|------|------|
| `ranking/best` | `ranking/best.py` | GET | 最佳成绩 |
| `ranking/list` | `ranking/list.py` | GET | 排行榜 |
| `ranking/event` | `ranking/event.py` | GET | 活动排名 |
| `ranking/global` | `ranking/global.py` | GET | 全球排名 |
| `ranking/player/all` | `ranking/player/all.py` | GET | 全部排名 |
| `ranking/player/rank` | `ranking/player/rank.py` | GET | 玩家段位 |
| `ranking/score/submit` | `ranking/score/submit.py` | POST | 提交成绩 |
| `ranking/score/record` | `ranking/score/record.py` | POST | 成绩记录 |

### 社区 (community)

| API 路径 | 实现文件 | 方法 | 说明 |
|----------|---------|------|------|
| `community/chart/info` | `community/chart/info.py` | GET | 谱面详情 |
| `community/chart/create` | `community/chart/create.py` | POST | 创建谱面 |
| `community/chart/online` | `community/chart/online.py` | GET | 在线谱面 |
| `community/chart/like` | `community/chart/like.py` | POST | 点赞谱面 |
| `community/chart/donate` | `community/chart/donate.py` | POST | 赞助谱面 |
| `community/chart/hash` | `community/chart/hash.py` | POST | 更新哈希 |
| `community/chart/promote` | `community/chart/promote.py` | POST | 推广谱面 |
| `community/chart/type` | `community/chart/type.py` | POST | 设置类型 |
| `community/player/chart` | `community/player/chart.py` | GET | 玩家谱面 |
| `community/song/create` | `community/song/create.py` | POST | 创建歌曲 |
| `community/song/info` | `community/song/info.py` | GET | 歌曲信息 |
| `community/song/cover` | `community/song/cover.py` | POST | 上传封面 |
| `community/wiki` | `community/wiki.py` | GET/POST | Wiki |
| `community/skin/buy` | `community/skin/buy.py` | POST | 购买公共皮肤 |

### 商店 (store)

| API 路径 | 实现文件 | 说明 |
|----------|---------|------|
| `store/list` | `store/list.py` | 商店列表 |
| `store/info` | `store/info.py` | 商店信息 |
| `store/charts` | `store/charts.py` | 谱面列表 |
| `store/choice` | `store/choice.py` | 精选 |
| `store/events` | `store/events.py` | 活动列表 |
| `store/event` | `store/event.py` | 单个活动 |
| `store/friend` | `store/friend.py` | 好友商店 |
| `store/promote` | `store/promote.py` | 推广 |
| `store/query` | `store/query.py` | 搜索 |
| `store/download` | `store/download.py` | 下载 |
| `store/upload/sign` | `store/upload/sign.py` | 上传签名 |
| `store/upload/finish` | `store/upload/finish.py` | 完成上传 |
| `store/upload` | `store/upload.py` | 完整上传流程 |

### 皮肤 (skin)

| API 路径 | 实现文件 | 说明 |
|----------|---------|------|
| `skin/list` | `skin/list.py` | 皮肤列表 |
| `skin/check` | `skin/check.py` | 检查皮肤 |
| `skin/buy` | `skin/buy.py` | 购买皮肤 |
| `skin/upload/sign` | `skin/upload/sign.py` | 上传签名 |
| `skin/upload/getid` | `skin/upload/getid.py` | 获取 ID |
| `skin/upload/finish` | `skin/upload/finish.py` | 完成上传 |

### 评论 (comment)

| API 路径 | 实现文件 | 说明 |
|----------|---------|------|
| `comment/list` | `comment/list.py` | 评论列表 |
| `comment/add` | `comment/add.py` | 添加评论 |
| `comment/delete` | `comment/delete.py` | 删除评论 |

### 审核 (review)

| API 路径 | 实现文件 | 说明 |
|----------|---------|------|
| `review/list` | `review/list.py` | 审核列表 |
| `review/add` | `review/add.py` | 添加审核 |
| `review/delete` | `review/delete.py` | 删除审核 |
| `review/status` | `review/status.py` | 状态变更 |
| `review/reply` | `review/reply.py` | 审核回复 |
| `review/queue` | `review/queue.py` | 审核队列 |
| `review/charts` | `review/charts.py` | 谱面审核 |
| `review/action` | `review/action.py` | 审核操作 |
| `review/my` | `review/my.py` | 我的审核 |

### 其他

| API 路径 | 实现文件 | 说明 |
|----------|---------|------|
| `dan/list` | `dan/list.py` | 段位列表 |
| `dan/all` | `dan/all.py` | 所有段位 |
| `achieve/player/all` | `achieve/player/all.py` | 成就列表 |
| `quest/list` | `quest/list.py` | 任务列表 |
| `puzzle/player/all` | `puzzle/player/all.py` | 拼图进度 |
| `push/info/wt` | `push/info.py` | 系统信息 |
| `push/message` | `push/message.py` | 消息推送 |
| `upload/skin/cover` | `upload/skin/cover.py` | 皮肤封面 |

---

## 目录结构

```
MalodyVClientPlugin/
├── .env                      # 环境变量配置（Nonebot2 标准）
├── __init__.py               # 插件入口，数据库生命周期
├── config.json               # 插件配置
├── user_data.db              # SQLite 数据库
├── cache/
│   └── ma_help.png           # 帮助图片缓存
├── MalodyAPI/                # API 封装层
│   ├── core.py               # 公共请求工具 + 环境变量读取
│   ├── database.py           # 数据库操作
│   ├── account/             # 账号相关 API
│   ├── player/              # 玩家相关 API
│   ├── ranking/             # 排行相关 API
│   ├── community/           # 社区相关 API
│   ├── store/               # 商店相关 API
│   ├── skin/                # 皮肤相关 API
│   ├── comment/             # 评论相关 API
│   ├── review/              # 审核相关 API
│   ├── dan/                 # 段位相关 API
│   ├── achieve/             # 成就相关 API
│   ├── quest/               # 任务相关 API
│   ├── puzzle/              # 拼图相关 API
│   ├── push/                # 推送相关 API
│   └── upload/              # 上传相关 API
├── matcher/                 # 命令匹配层
│   ├── __init__.py
│   ├── login.py             # /login 命令
│   ├── mm.py                # /mm 命令
│   ├── mmbest.py            # /mb 命令
│   ├── ma.py                # /ma 命令调度器
│   ├── mm_ocr.py            # OCR 命令
│   └── handler/             # 业务处理层
│       ├── user_utils.py    # 用户凭证工具
│       ├── login_handler.py # 登录处理
│       ├── mm_handler.py    # 分数计算处理
│       ├── mmbest_handler.py# Best 查询处理
│       ├── ma_help.py       # 帮助
│       ├── ma_profile.py    # 资料
│       ├── ma_search.py     # 搜索
│       ├── ma_rank.py       # 段位
│       ├── ma_dan.py        # 段位记录
│       ├── ma_global.py     # 全球排行
│       ├── ma_store.py      # 商店
│       ├── ma_event.py      # 活动
│       ├── ma_chart.py      # 谱面
│       ├── ma_song.py       # 歌曲
│       ├── ma_wiki.py       # Wiki
│       ├── ma_friend.py     # 好友
│       ├── ma_achieve.py    # 成就
│       ├── ma_quest.py      # 任务
│       ├── ma_news.py       # 消息
│       └── ma_logout.py     # 登出
└── render/                  # 消息渲染层
    ├── mmbest.py            # Best 成绩图片渲染
    ├── profile.py           # 玩家资料图片渲染
    └── help_image.py        # 帮助图片渲染
```

---

## 架构说明

本插件采用三层架构：

1. **MalodyAPI/** — 纯 Python API 封装，每个 API 端点独立一个文件，使用同步 `requests` 调用
2. **matcher/handler/** — 业务处理层，通过 `asyncio.to_thread` 调用同步 API，处理参数解析、数据聚合
3. **render/** — 消息渲染层，使用 Pillow 可组合组件（Card/ListView/ProfileCard/ChartCard），支持封面/头像/表格图片
4. **matcher/*.py** — Nonebot 命令匹配器，负责将 QQ 消息路由到对应的 handler

翻页机制：
- 所有列表类命令通过 `core._paginate()` 自动循环 `hasMore`/`next` 分页
- 用户只需指定目标数量（如 `ma store 100`），无需手动翻页

认证方式：
- **access_token** (登录态 token)：用于需要登录的 API，通过 `?key=token&uid=uid` 传递
- **store_token**：用于商店/皮肤相关 API，通过 `?api=202409&uid=uid&key=store_token` 传递

## 依赖

- nonebot2 >= 2.0.0
- nonebot-adapter-onebot >= 2.0.0
- aiosqlite
- httpx
- Pillow
- requests

## 配置

插件使用 Nonebot2 标准 `.env` 文件管理环境变量，**无需手动编辑代码**。

`.env` 示例（放置在插件根目录 `MalodyVClientPlugin/.env`）：

```ini
# Malody API 配置
MALODY_API_BASE=https://api.mugzone.net
MALODY_VERSION=6.6.43
MALODY_VER=394795
MALODY_STORE_API=202409

# API 请求超时 (秒)
MALODY_TIMEOUT=10
```

所有变量均可通过 `nonebot.get_driver().config` 读取，默认值已内置在 `core.py` 中，不配置也能运行。

### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MALODY_API_BASE` | `https://api.mugzone.net` | API 服务器地址 |
| `MALODY_VERSION` | `6.6.43` | 客户端版本号，影响 User-Agent |
| `MALODY_VER` | `394795` | 内部版本号，用于登录 bver 计算 |
| `MALODY_STORE_API` | `202409` | Store API 密钥 |
| `MALODY_TIMEOUT` | `10` | HTTP 请求超时（秒） |

### 数据库设计

`user_data.db` 中的 `user_bind` 表：

| 列名 | 类型 | 说明 |
|------|------|------|
| `uid` | TEXT (PK) | Malody 用户 UID |
| `qq` | TEXT | 绑定的 QQ 号 |
| `username` | TEXT | 用户名 |
| `access_token` | TEXT | 登录态 token（用于登录 API） |
| `store_token` | TEXT | Store token（用于商店 API） |
| `refresh_token` | TEXT | 刷新令牌 |
| `device_id` | TEXT | 设备标识 |
| `is_login` | INT | 是否已登录 |
| `login_count` | INT | 登录次数 |
| `last_login_time` | REAL | 最后登录时间戳 |
| `avatar` | TEXT | 头像哈希 |
| `gold` | INT | 金币 |
| `group_list` | TEXT (JSON) | 用户组 |
| `extra` | TEXT (JSON) | 扩展字段 |

Token 在登录成功后自动持久化，插件重启无需重新登录。

## 数据来源

所有 API 实现基于 [Emiria](https://github.com/Mugzone/Emiria) 官方客户端源码中的 `ClientHttp.cs`、`Enums.cs`、`ClientHttp.PackFactory.cs` 及 `MaApi/*.cs` 响应类型定义。

---

## 本次工作总结

基于 Emiria 官方源码，完整实现 MalodyVClientPlugin：

1. **API 全覆盖**：80+ 个端点，从占位到完整实现
2. **Bot 指令**：36 个子命令，每个都有对应的 matcher/handler
3. **登录校验**：所有 `ma` 子命令统一要求先登录
4. **帮助系统**：`ma help` 生成分类帮助图片并缓存
5. **图片渲染**：profile、help 图片渲染
6. **环境变量**：Nonebot2 `.env` 标准配置
7. **代码规范**：所有 API 通过 `core._get/_post`，消除重复
