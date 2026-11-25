# Baka666Bot

NoneBot2 QQ bot，通过 NapCat 接入 OneBot V11。

## Requirements

- Windows 10/11 x64
- [uv](https://docs.astral.sh/uv/)
- Git + Git LFS
- NapCat（解压到 `NapCat.Shell\`）

## Setup

```powershell
git lfs install
git clone --recurse-submodules https://github.com/InFengQwQ/Baka666bot.git
cd Baka666bot
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
```

Chromium 由 Playwright 安装，不再随仓库分发。

编辑 `.env`，设置 `SUPERUSERS` 和 `PORT`。NapCat 反向 WebSocket 指向：

```text
ws://127.0.0.1:9090/onebot/v11/ws
```

## NapCat

- 版本 4.18.42，解压到 `NapCat.Shell\`，入口 `NapCat.Shell\napcat.bat`
- 下载：<https://github.com/InFengQwQ/Baka666bot/releases/download/napcat-4.18.42/NapCat.Shell-4.18.42-win64.zip>
- sha256：`74cf1b90ca718b23230eff978f9359ddc522e9db428bb3a6a30c9722ad77d896`

## Run

```powershell
.\start.bat
```

`start.bat` 先启动 NapCat，再在前台运行 bot。`NAPCAT_QQ` 留空时用二维码登录。

## Commands

[COMMANDS.md](COMMANDS.md)

上游：<https://github.com/MCPsDE/Baka666bot>。第三方插件与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
