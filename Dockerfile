FROM python:3.12-slim
WORKDIR /app

# Install system dependencies required for some python packages (like sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY silex/ ./silex/
COPY scripts/ ./scripts/
COPY skills/ ./skills/

# Install python dependencies
RUN pip install --no-cache-dir -e ".[mcp]" \
    && python -m playwright install --with-deps chromium

# Set up the data directory for the SQLite database
RUN mkdir -p data workspace \
    && useradd --create-home --shell /usr/sbin/nologin kinthic \
    && chown -R kinthic:kinthic /app

USER kinthic

# Default command: run the cli directly, usually overridden by docker-compose
CMD ["kinthic", "--help"]

