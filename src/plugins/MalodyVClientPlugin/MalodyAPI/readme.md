# Malody API 参考

所有 API 均基于 `https://api.mugzone.net/api/` 前缀，请求通常携带 `?key=<store_token>&uid=<uid>&t=<timestamp>` 等公共参数。

| 分类 | API 路径 | 字符串常量地址 (IDA) | 说明 |
|------|----------|---------------------|------|
| **账号** | `account/login/wt` | `StringLiteral_126` | 登录接口 |
| | `account/register/wt` | `StringLiteral_140` | 注册 |
| | `account/renew` | `StringLiteral_147` | 刷新令牌 |
| | `account/logout` | `StringLiteral_133` | 登出 |
| | `account/deletion` | `StringLiteral_119` | 注销账号 |
| **玩家** | `player/info` | `StringLiteral_6650` | 完整信息 |
| | `player/info/simple` | `StringLiteral_6657` | 简要信息 |
| | `player/items` | `StringLiteral_6664` | 道具 |
| | `player/ring` | `StringLiteral_6685` | 环模式数据 |
| | `player/slot` | `StringLiteral_6699` | 插槽 |
| | `player/marlo` | `StringLiteral_6671` | Marlo 记录 |
| | `player/image` | `StringLiteral_6643` | 上传头像 |
| | `player/search` | `StringLiteral_6692` | 搜索玩家 |
| | `player/friend` | `StringLiteral_6629` | 好友列表 |
| | `player/friend/toggle` | `StringLiteral_6636` | 添加/删除好友 |
| | `player/mute` | `StringLiteral_6678` | 禁言/屏蔽 |
| **排名** | `ranking/best` | `StringLiteral_7840` | 最佳成绩 |
| | `ranking/global` | `StringLiteral_7854` | 全球排名 |
| | `ranking/list` | `StringLiteral_7861` | 排行榜列表 |
| | `ranking/event` | `StringLiteral_7847` | 活动排名 |
| | `ranking/player/rank` | `StringLiteral_7875` | 玩家段位 |
| | `ranking/player/all` | `StringLiteral_7868` | 全部排名 |
| | `ranking/score/record` | `StringLiteral_7882` | 成绩记录 |
| | `ranking/score/submit` | `StringLiteral_7889` | 提交成绩 |
| **成就/任务** | `achieve/player/all` | `StringLiteral_154` | 成就列表 |
| | `puzzle/player/all` | `StringLiteral_7532` | 拼图进度 |
| | `quest/list` | `StringLiteral_7630` | 任务列表 |
| **社区** | `community/chart/info` | `StringLiteral_5625` | 谱面详情 |
| | `community/chart/create` | `StringLiteral_5604` | 创建谱面 |
| | `community/chart/online` | `StringLiteral_5639` | 在线谱面 |
| | `community/chart/hash` | `StringLiteral_5618` | 谱面哈希 |
| | `community/chart/like` | `StringLiteral_5632` | 点赞谱面 |
| | `community/chart/promote` | `StringLiteral_5646` | 推广谱面 |
| | `community/chart/donate` | `StringLiteral_5611` | 赞助谱面 |
| | `community/chart/type` | `StringLiteral_5653` | 谱面类型 |
| | `community/player/chart` | `StringLiteral_5660` | 玩家谱面 |
| | `community/song/create` | `StringLiteral_5681` | 创建歌曲 |
| | `community/song/info` | `StringLiteral_5688` | 歌曲信息 |
| | `community/song/cover` | `StringLiteral_5674` | 歌曲封面 |
| | `community/wiki` | `StringLiteral_5695` | Wiki |
| | `community/skin/buy` | `StringLiteral_5667` | 购买皮肤 |
| **评论/审核** | `comment/add` | `StringLiteral_5583` | 发表评论 |
| | `comment/delete` | `StringLiteral_5590` | 删除评论 |
| | `comment/list` | `StringLiteral_5597` | 评论列表 |
| | `review/add` | `StringLiteral_8659` | 添加审核 |
| | `review/delete` | `StringLiteral_8673` | 删除审核 |
| | `review/list` | `StringLiteral_8680` | 审核列表 |
| | `review/my` | `StringLiteral_8687` | 我的审核 |
| | `review/charts` | `StringLiteral_8666` | 谱面审核 |
| | `review/status` | `StringLiteral_8708` | 审核状态 |
| | `review/queue` | `StringLiteral_8694` | 审核队列 |
| | `review/reply` | `StringLiteral_8701` | 审核回复 |
| | `review/action` | `StringLiteral_8652` | 审核操作 |
| **皮肤** | `skin/list` | `StringLiteral_11017` | 皮肤列表 |
| | `skin/check` | `StringLiteral_11010` | 检查皮肤 |
| | `skin/buy` | `StringLiteral_11003` | 购买皮肤 |
| | `skin/upload/sign` | `StringLiteral_11038` | 皮肤上传签名 |
| | `skin/upload/getid` | `StringLiteral_11031` | 获取上传 ID |
| | `skin/upload/finish` | `StringLiteral_11024` | 完成皮肤上传 |
| **商店** | `store/list` | `StringLiteral_12143` | 商店列表 |
| | `store/info` | `StringLiteral_12136` | 商店详情 |
| | `store/charts` | `StringLiteral_12094` | 商店谱面 |
| | `store/choice` | `StringLiteral_12101` | 精选 |
| | `store/events` | `StringLiteral_12122` | 活动 |
| | `store/event` | `StringLiteral_12115` | 单个活动 |
| | `store/friend` | `StringLiteral_12129` | 好友商店 |
| | `store/promote` | `StringLiteral_12150` | 推广 |
| | `store/query` | `StringLiteral_12157` | 查询 |
| | `store/download` | `StringLiteral_12108` | 下载 |
| | `store/upload/sign` | `StringLiteral_12171` | 上传签名 |
| | `store/upload/finish` | `StringLiteral_12164` | 完成上传 |
| **其他** | `push/message` | `StringLiteral_7504` | 推送消息 |
| | `push/info/wt` | `StringLiteral_7497` | 推送信息 |
| | `dan/all` | `StringLiteral_8880` | 段位列表 |
| | `dan/list` | `StringLiteral_8887` | 段位详情 |
| | `upload/skin/cover` | `StringLiteral_16327` | 皮肤封面 |

> 注：字符串常量地址可在 IDA 中通过 `Shift+F12` 搜索字符串后，双击跳转至对应数据段，再通过交叉引用（`Ctrl+X`）追踪到构造请求的函数（通常是 `Malody_Network_bato__bbth` 或 `Malody_Network_bawp__Setup`）。