FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install system dependencies needed to build pygame-ce and jq
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    autoconf \
    libtool \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached unless lock file changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application code and install the project itself
COPY grydgets/ grydgets/
COPY main.py README.md ./
RUN uv sync --frozen


FROM python:3.12-slim-bookworm

WORKDIR /app

# Install runtime SDL2 libraries (no -dev packages needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code (needed for main.py shim)
COPY grydgets/ grydgets/
COPY main.py ./

ENV PATH="/app/.venv/bin:$PATH"
ENV SDL_VIDEODRIVER=dummy
ENV SDL_AUDIODRIVER=dummy

EXPOSE 5000

ENTRYPOINT ["grydgets"]
CMD ["--config-dir", "/data"]
