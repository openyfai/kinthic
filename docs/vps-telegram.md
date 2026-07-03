# Kronos VPS & Telegram Deployment Guide

This guide explains how to deploy Kronos on a standard Ubuntu Linux VPS (Virtual Private Server) using Docker Compose and connect it to Telegram.

## 1. Prerequisites

- A fresh Ubuntu 22.04 or 24.04 VPS (1GB+ RAM recommended).
- A Telegram Bot Token from [@BotFather](https://t.me/botfather).
- An LLM Provider API Key (e.g., Gemini API key, Anthropic API key).

## 2. Server Setup

SSH into your VPS and install Docker:

```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker $USER
```
*(Log out and log back in to apply docker group changes)*

## 3. Clone and Configure

Clone the Kronos repository:

```bash
git clone https://github.com/openyfai/kronos.git
cd kronos
```

Create a `.env` file to store your API keys. Make sure it contains your Telegram bot token and preferred LLM provider key:

```bash
cat << 'EOF' > .env
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
EOF
```

## 4. Launch Kronos

Use Docker Compose to build and start Kronos in detached mode.

```bash
docker compose --profile telegram up -d --build
```

Kronos is now running! The `kronos-data` docker volume securely persists your brain (`silex.db`), skills, and configuration at `/home/kronos/.kronos` inside the container.

## 5. Pair via Telegram

1. Open Telegram and search for your bot.
2. Send the `/start` command.
3. Send `/pair` to link your Telegram account to Kronos.
4. You are now the exclusive operator of this Kronos instance. 

## 6. Maintenance Commands

To view logs:
```bash
docker compose logs -f
```

To stop Kronos:
```bash
docker compose --profile telegram down
```

To backup your Kronos data, run the `backup export` command using `docker exec`:
```bash
docker exec -it kronos-telegram kronos backup export
```
Then copy the zip file out of the container to your host system:
```bash
docker cp kronos-telegram:/app/kronos-backup.zip ./kronos-backup.zip
```
*(Note: `secrets.json` is safely excluded from backups to prevent credential leakage).*
