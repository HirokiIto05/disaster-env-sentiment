# ============================================================
# Environment
# Base: python:3.12-slim-bookworm
# Added: R 4.4 (CRAN official), Quarto, VS Code dev-container compatible
# ============================================================
FROM python:3.12-slim

# ── System dependencies ──────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Utilities
    curl \
    wget \
    git \
    # Required to add CRAN repository
    ca-certificates \
    dirmngr \
    gnupg \
    # R build dependencies
    libssl-dev \
    libcurl4-openssl-dev \
    libxml2-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages ───────────────────────────────────────────
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip --quiet \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# ── Quarto ────────────────────────────────────────────────────
ARG QUARTO_VERSION=1.5.57
RUN QUARTO_ARCH="$(dpkg --print-architecture)" \
        && case "$QUARTO_ARCH" in \
            amd64|arm64) ;; \
            *) echo "Unsupported architecture: $QUARTO_ARCH" >&2; exit 1 ;; \
        esac \
        && wget -q "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${QUARTO_ARCH}.deb" \
            -O /tmp/quarto.deb \
        && dpkg -i /tmp/quarto.deb \
        && rm /tmp/quarto.deb

# ── Working directory ─────────────────────────────────────────
WORKDIR /workspace

# ── Default command ───────────────────────────────────────────
CMD ["bash"]