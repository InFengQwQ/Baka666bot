# Bakahelp

独立 Git 仓库中的 NoneBot2 本地插件。仅当消息去除开头空白后以 `/` 开头时，自动提示一次：

```text
Baka666bot使用帮助:malody.top/bakahelp
发送 TD 可关闭本群自动帮助提示。
```

发送 `TD`（也支持 `/TD`、小写）会关闭整个群的自动提示，持久保存到 `data/Bakahelp/preferences.sqlite3`，不影响正常指令。主动发送 `help`、`bakahelp` 或对应斜杠命令仍可查看帮助。私聊的 TD 仅影响该用户的私聊提示。配置项 `BAKAHELP_PREFERENCES_PATH` 可更改保存路径。

自动提示不阻断业务响应；同一条消息仅提示一次。普通聊天、非斜杠指令、网址和文字中间的斜杠不会自动提示。

`free_egg.py` 通过 QQ 群消息上的蛋表情去重。每个运行实例的 Bot 都需启用此插件。处理 `/` 开头的群消息时，Bot 先查看同一条消息是否已有这枚表情：有则拦截本 Bot 的后续命令处理，没有则贴蛋后继续。先贴蛋的 Bot 处理指令，同群中的其他 Bot 看到蛋后会跳过。此机制用于 QQ OneBot V11 群聊。Bot 自身发出的消息和非斜杠消息不参与；表情接口异常时会放行消息，保持指令可用。

网页优先展示 Malody / osu!，支持搜索、插件/触发类型筛选、说明筛选、复制命令、移动端布局。生成的 `dist/index.html` 内嵌全部 CSS、JS 和数据，可以保存后直接打开，不依赖 CDN。

## 自动收录

在 Bot 启动、Bot 连接时读取实际已注册的 Matcher；同时支持手动构建。涵盖 `on_command`、别名、元组子命令/CommandGroup、`on_shell_command`、`on_fullmatch`、`on_startswith`、`on_endswith`、`on_keyword`、`on_regex`、Alconna 及其快捷规则、消息/通知/请求等事件。`ma`、`/omtk` 等共享入口的分派子命令从其实际运行时分派表及内置帮助数据补充。使用实际 `command_start` / `command_sep`；无须为第三方插件改源码。

只收录已经加载并注册的响应器，临时会话响应器被排除。未启用、加载失败的插件不算可用功能；只有依赖功能的插件可能没有独立条目。启动日志应确认全部预期插件加载成功。动态注册的内容会在下次连接或导出时更新。

任意 Python 自定义规则、处理函数中的分支、权限复合判断、运行时用户上下文不能可靠还原为完整用法。`manual.json` 可通过 handler 或命令覆盖补充可读语义。页面用自然语言说明已知消息格式和事件条件，不展示原始正则表达式。权限提示不能替代真实权限检查。自动生成的参数帮助只来自插件自己的 parser / Alconna 元数据。

`nonebot_plugin_memes` 的数百个模板触发项由插件运行时元数据生成，并在网页和 Markdown 中折叠展示，避免长目录挤占其他功能。

## 手写说明

编辑 `manual.json`，生成不会覆盖此文件。三种粒度，优先级由低到高：

1. `plugins.<插件ID>`：名称、分类、描述；`defaults` 为该插件的条目默认说明。
2. `triggers`：用 `plugin` 和 `match`（实际触发字符串数组，例如 `["/sm"]`）匹配；适合同一功能不同别名/不同前缀的文案。
3. `entries.<条目ID>`：精确覆盖，ID 可在网页“用法与触发详情”中找到。

说明字段：`title`、`description`、`usage`、`examples`（字符串数组）、`notes`、`audience`、`hidden`（设为 true 不发布此条目）。不填说明时明确显示“详细用法待补充”。所有文案按纯文本渲染，不支持 HTML。

```json
{"plugin":"Malody_toolkit","match":["/sm"],"title":"搜索谱面","usage":"/sm <歌曲关键词>","examples":["/sm conflict"]}
```

## 构建与验证

在 Bot 项目根目录运行：

```powershell
venv/Scripts/python.exe src/plugins/Bakahelp/build.py --bot-root .
venv/Scripts/python.exe -m unittest discover -s src/plugins/Bakahelp/tests -v
```

构建会导入正常的 `bot.py`，但不会运行 Bot 驱动、启动钩子或连接聊天平台。插件导入自身仍可能初始化数据或缓存，需要与正常 Bot 相同的依赖和文件权限。

启动自动输出默认位于插件 `dist/`，可在 `.env` 设置 `BAKAHELP_OUTPUT_DIR`。生成写入采用原子替换；失败保留旧 HTML，Bot 继续启动。

## 部署：通过 MalodySite 的 GitHub main

正式站点仓库是 MCPsDE/MalodySite，生产源码在 /root/MalodySite。请遵循该仓库的 AGENTS.md 和 ops/README.md。

先构建，再将网页导出到一个干净的 MalodySite 源码工作区：

```powershell
venv/Scripts/python.exe src/plugins/Bakahelp/build.py --bot-root .
venv/Scripts/python.exe src/plugins/Bakahelp/export_site.py --site-root <MalodySite源码目录>
```

导出器只更新 public/bakahelp/ 下的静态内容，将字体和 favicon 转为本地独立资源，保留字体许可证。离线的 dist/index.html 仍是单文件版本。

检查站点 diff，运行站点规范要求的检查，提交并推送已授权的 GitHub main 更新。然后在服务器运行 /usr/local/sbin/malody-update，由正式流程构建发布和执行健康检查。不要向线上目录直接上传文件，也不要通过独立的 Caddy 路由部署此页面。旧的直接 SSH 上传工具已移除。

站点的 /bakahelp Vue 路由负责转到同源 /bakahelp/index.html，防止站内导航进入自定义 404 页。验收要检查实际标题、目录和交互，不能只看 HTTP 200。

Bot 启动/连接会自动更新本地网页和 `COMMANDS.md`；插件或说明变化后，需要把当前构建导出到 MalodySite 源码仓库、审查搜索与分类功能，再通过站点正式发布流程部署。详见站点 docs/BAKAHELP.md。

旧 src/plugins/help.py 及跨平台插件中的旧帮助响应器已移除。新插件由 src/plugins 自动加载，正在运行的 Bot 需要重启一次。
