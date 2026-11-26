# Baka666Bot

NoneBot2 QQ bot，通过 NapCat 接入 OneBot V11。

## Windows

需要 Windows 10/11 x64、[uv](https://docs.astral.sh/uv/)、Git、Java 11+ 和 FFmpeg：

```powershell
winget install EclipseAdoptium.Temurin.17.JRE
winget install Gyan.FFmpeg
git clone --recurse-submodules https://github.com/InFengQwQ/Baka666bot.git
cd Baka666bot
uv sync
uv run playwright install chromium
uv run python scripts/fetch-assets.py
Copy-Item .env.example .env
```

`java` 按 `JAVA_HOME`、`PATH` 的顺序查找，`ffmpeg`、`ffprobe` 从 `PATH` 查找。渲染器和转换工具由 `scripts/fetch-assets.py` 下载，`start.bat` 发现缺失时会自动补。

NapCat 4.18.42 解压到 `NapCat.Shell\`：<https://github.com/InFengQwQ/Baka666bot/releases/download/napcat-4.18.42/NapCat.Shell-4.18.42-win64.zip>，sha256 `74cf1b90ca718b23230eff978f9359ddc522e9db428bb3a6a30c9722ad77d896`。

在 `.env` 里设置 `SUPERUSERS` 和 `PORT`，把 NapCat 的反向 WebSocket 指向 `ws://127.0.0.1:9090/onebot/v11/ws`，然后运行 `.\start.bat`。`NAPCAT_QQ` 留空时改用二维码登录。

## Docker

```bash
git clone https://github.com/InFengQwQ/Baka666bot.git
cd Baka666bot
cp .env.example .env
docker compose pull
docker compose up -d
```

镜像已含 Java、FFmpeg、wine、Chromium 和渲染器，宿主机不需要安装。NapCat WebUI 在 <http://127.0.0.1:6099>，反向 WebSocket 设为 `ws://bot:9090/onebot/v11/ws`。`.env` 里填 `NAPCAT_QQ` 后重启不再扫码，第一次仍需登录一次；留空则每次扫码。

命令见 [COMMANDS.md](COMMANDS.md)。上游：<https://github.com/MCPsDE/Baka666bot>。第三方插件与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
