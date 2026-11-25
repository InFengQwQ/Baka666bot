FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# pythonnet (osu-tools-py) needs a .NET runtime.
RUN curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/ms.deb \
    && dpkg -i /tmp/ms.deb \
    && rm /tmp/ms.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends dotnet-runtime-8.0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

RUN uv run playwright install --with-deps chromium

COPY . .

RUN ln -sf /usr/bin/ffmpeg src/plugins/Malody_toolkit/tools/ffmpeg.exe \
    && ln -sf /usr/bin/ffprobe src/plugins/Malody_toolkit/tools/ffprobe.exe \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app

CMD ["sh", "-c", "uv run python docker/migrate.py && exec uv run bot.py"]
