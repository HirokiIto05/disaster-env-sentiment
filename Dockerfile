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

# ── R 4.4 via CRAN official repository ───────────────────────
# RUN curl -fsSL https://cloud.r-project.org/bin/linux/debian/marutter_pubkey.asc \
#         | gpg --dearmor -o /usr/share/keyrings/cran.gpg \
#     && echo "deb [signed-by=/usr/share/keyrings/cran.gpg] https://cloud.r-project.org/bin/linux/debian bookworm-cran44/" \
#         > /etc/apt/sources.list.d/cran.list \
#     && apt-get update && apt-get install -y --no-install-recommends \
#         r-base=4.4* \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*

# ── Python packages ───────────────────────────────────────────
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip --quiet \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# ── Quarto ────────────────────────────────────────────────────
ARG QUARTO_VERSION=1.5.57
RUN wget -q "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb" \
    -O /tmp/quarto.deb \
    && dpkg -i /tmp/quarto.deb \
    && rm /tmp/quarto.deb

# ── R packages ────────────────────────────────────────────────
# RUN R -e "\
#   install.packages(c( \
#     'renv', 'languageserver', 'httpgd' \
#   ), repos='https://cloud.r-project.org') \
# "

# ── Package cache & permission ────────────────────────────────
# RUN mkdir -p /root/.cache \
#     && chown root:root /root/.cache

# ── Working directory ─────────────────────────────────────────
WORKDIR /workspace

# ── Default command ───────────────────────────────────────────
CMD ["bash"]