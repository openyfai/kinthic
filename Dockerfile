# Stage 1: Build the Next.js UI
FROM node:20-slim AS ui-builder
WORKDIR /app
COPY aria-ui/package*.json ./aria-ui/
WORKDIR /app/aria-ui
RUN npm ci
COPY aria-ui/ ./
RUN npm run build

# Stage 2: Build the Python backend
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies required for some python packages (like sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY aria/ ./aria/
COPY scripts/ ./scripts/
COPY skills/ ./skills/

# Copy the built UI from Stage 1
COPY --from=ui-builder /app/aria-ui/out ./aria-ui/out

# Install python dependencies
RUN pip install --no-cache-dir -e "." \
    && python -m playwright install --with-deps chromium

# Set up the data directory for the SQLite database
RUN mkdir -p data workspace \
    && useradd --create-home --shell /usr/sbin/nologin aria \
    && chown -R aria:aria /app

USER aria

# Expose the Web Graph UI port
EXPOSE 8000

# The default command will run the Web Graph server.
# To run the telegram bot, users can override the command in docker-compose.
CMD ["python", "scripts/web_server.py"]
