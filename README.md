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

需要 Windows、Git、Git LFS、Python 3.10+、已安装的 QQ 客户端和 NapCat。克隆时要初始化插件子模块并下载运行资源：

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

## 更新模式

默认不设置额外变量时，启动过程会检查公开仓库 `MCPsDE/Baka666bot` 的 `main`。发现新版本后会同步主仓库、插件子模块和 Git LFS 资源，再重启机器人。更新会用远端版本替换受 Git 管理的本地文件，并清理未忽略的多余文件；`.env`、`config/*.env`、`data/` 等被忽略的本地配置和运行数据会保留。

本地开发或测试期间，在 `.env` 中设置以下值可关闭自动拉取：

```dotenv
BAKA666BOT_UPDATE_MODE=dev
```

发布并希望本地实例恢复自动更新时，删除这一行即可。该变量不在 `.env.example` 中提供。

Playwright 所需 Chromium headless shell、Malody Toolkit 使用的 Java 与 FFmpeg 均保存在项目目录中。机器人数据、账户数据库和缓存写入 `data/`。

## 第三方许可

机器人包含独立维护的第三方插件 fork。各插件上游、分支和许可信息见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。许可证文本保存在 `licenses/` 和各插件目录中。

