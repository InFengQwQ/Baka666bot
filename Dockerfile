FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV LANG=C.UTF-8 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WINEPREFIX=/home/app/.wine

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg fonts-wqy-zenhei openjdk-17-jre-headless wine \
    && rm -rf /var/lib/apt/lists/*

# pythonnet (osu-tools-py) needs a .NET runtime.
RUN curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/ms.deb \
    && dpkg -i /tmp/ms.deb \
    && rm /tmp/ms.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-runtime-8.0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app /ms-playwright \
    && chown app:app /app /ms-playwright

WORKDIR /app
COPY --chown=app:app pyproject.toml uv.lock ./

USER app
RUN uv sync --frozen --no-dev \
    && rm -rf /home/app/.cache/uv

# Create the wine prefix at build time so the first command does not pay for it.
RUN WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=" wine wineboot -u \
    && test -f /home/app/.wine/drive_c/windows/system32/kernel32.dll

USER root
RUN /app/.venv/bin/playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

USER app
RUN /app/.venv/bin/playwright install --only-shell chromium

COPY --chown=app:app . .

# The plugins live in submodules; fail the build instead of publishing an
# image without them.
RUN test -f src/plugins/nonebot_plugin_osubot/__init__.py \
    && test -f src/plugins/nonebot_plugin_osugreek/__init__.py \
    && test -f src/plugins/nonebot_plugin_osumania_toolkit/__init__.py \
    && test -f src/plugins/nonebot-plugin-for-osumania4k/nonebot_plugin_rework/__init__.py

RUN python scripts/fetch-assets.py --platform linux

# A fresh named volume inherits this directory's owner (app, uid 1000).
# Logs go under the volume so they survive container recreation.
RUN mkdir -p data/logs && ln -s data/logs logs

CMD ["sh", "-c", "uv run python docker/migrate.py && exec uv run bot.py"]
