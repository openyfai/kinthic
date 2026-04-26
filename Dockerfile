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

# Install python dependencies
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir fastapi uvicorn python-telegram-bot

# Set up the data directory for the SQLite database
RUN mkdir -p data

# Expose the Web Graph UI port
EXPOSE 8000

# The default command will run the Web Graph server.
# To run the telegram bot, users can override the command in docker-compose.
CMD ["python", "scripts/web_server.py"]
