<p align="center">
  <img src="assets/readme-banner.png" alt="Baka666Bot" width="100%">
</p>

<h1 align="center">Baka666Bot</h1>

<p align="center">
  <a href="https://github.com/MCPsDE/Baka666bot"><img src="https://img.shields.io/github/stars/MCPsDE/Baka666bot?style=social" alt="GitHub stars"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/NoneBot2-2.x-19A974" alt="NoneBot2">
</p>

面向音游社区的 NoneBot2 机器人，当前通过 OneBot V11 连接 QQ。项目以终端方式运行，内含 Malody、osu!mania、群管理、帮助和跨平台消息适配等插件。

把多个 Baka666Bot 拉进同一个 QQ 群不会造成重复回复，可以放心拉。每个 Bot 都启用群聊“贴蛋”后，会先检查当前消息上的 🥚 反应，已贴蛋的 Bot 不再触发这条斜杠指令。

Bot 连接时会检查总群并自动接受尚未处理的总群邀请。QQ 需要先收到群成员发出的邀请，Bot 才能加入群聊。

## 功能

- Malody V 账号与谱面 API、排行榜、谱面下载、猜曲和分数工具
- `.mc`、`.mcz`、`.osu`、`.osz` 与回放处理工具
- osu!mania 谱面分析、成绩卡片和预览
- QQ 群管理、帮助、群文件整理与贴纸功能
- Discord、Telegram 的跨平台适配代码，当前启动配置仅注册 OneBot V11

谱面格式转换指令支持以下别名：

- `/ma2om`、`/ma2osu`、`/mc2osu`、`/mc2om` 将 `.mc` 转为 `.osu`，也会把 `.mcz`、`.osz` 或 `.zip` 包内的 `.mc` 谱面转换后输出 `.osz`。
- `/om2ma`、`/osu2ma`、`/om2mc`、`/osu2mc` 将 `.osu` 转为 `.mc`，也会把 `.osz` 或 `.zip` 包内的 `.osu` 谱面转换后输出 `.mcz`。压缩包内被谱面引用的 MP3 会转为 OGG，并同步更新 `.mc` 音频引用。

## 运行

需要 Windows、Git、Git LFS、Python 3.10+、FFmpeg（`/mcz_speed`、`/timeinverse` 等音频处理）、已安装的 QQ 客户端和 NapCat。克隆时要初始化插件子模块并下载运行资源：

```powershell
git lfs install
git clone --recurse-submodules https://github.com/MCPsDE/Baka666bot.git
Set-Location Baka666bot
```

首次安装 Python 依赖：

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install -e .
```

音频处理命令需要 `ffmpeg` 和 `ffprobe`，可用 `winget install Gyan.FFmpeg` 安装并确保在 `PATH` 中。

只在对应配置文件不存在时创建本地配置：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path config\adapters.env)) { Copy-Item config\adapters.env.example config\adapters.env }
if (-not (Test-Path config\malody.env)) { Copy-Item config\malody.env.example config\malody.env }
```

在 `.env` 中设置 `SUPERUSERS` 和需要的 API 配置。`config/malody.env` 用于 Malody 下载账号配置。Discord、Telegram 配置保存在 `config/adapters.env`，但需要在启动入口启用相应适配器后才会连接。

先启动 NapCat：

```powershell
.\NapCat.Shell\launcher-user.bat
```

再在另一个终端启动机器人：

```powershell
.\venv\Scripts\python.exe bot.py
```


## 第三方许可

项目使用的第三方插件与工具，其来源、分支和许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。许可证文本保存在 `licenses/` 和各插件目录中。

## 赞助者

感谢支持 Baka666Bot 的 GitHub 用户。本文档编写、发布前的代码整理，以及发布后部分插件的开发过程中，使用了 @zhyzx35607 提供的 ChatGPT。

<p align="left">
  <a href="https://github.com/zhyzx35607"><img src="https://github.com/zhyzx35607.png?size=96" width="64" alt="zhyzx35607"></a>
</p>

## 参与改进

如果你想进行本地定制，欢迎先将希望加入的新功能或发现的 bug 提交到 GitHub Issue 讨论。准备好代码后，也欢迎将扩展功能整理为 Pull Request，方便一起审查和维护。

当前可触发指令见 [COMMANDS.md](COMMANDS.md)，也可在 [在线帮助页](https://malody.top/bakahelp) 搜索和筛选。

