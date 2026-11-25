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
Copy-Item .env.example .env
```

编辑 `.env`，设置 `SUPERUSERS` 和 `PORT`。NapCat 反向 WebSocket 指向：

```text
ws://127.0.0.1:9090/onebot/v11/ws
```

## Run

```powershell
.\NapCat.Shell\napcat.bat
uv run bot.py
```

## Commands

[COMMANDS.md](COMMANDS.md)

上游：<https://github.com/MCPsDE/Baka666bot>。第三方插件与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
