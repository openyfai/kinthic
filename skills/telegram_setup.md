---
name: telegram_setup
description: Pair a Telegram bot, configure allowlist, and run the Kronos daemon
metadata:
  trigger: telegram bot setup pair daemon messaging
---

# Telegram Setup Skill

## When to use
User asks to connect Telegram, run the bot, pair their account, or configure messaging.

## Workflow

1. Confirm `TELEGRAM_BOT_TOKEN` is set in `~/.kronos/.env` or secrets.
2. Run `kronos telegram pair` to generate a pairing code if no users are paired yet.
3. User sends `/start <CODE>` to the bot in Telegram.
4. Set `ALLOWED_TELEGRAM_USERS` in `~/.kronos/.env` with the paired chat id.
5. Start the bot with `kronos telegram run` or `kronos daemon` for 24/7 operation.
6. Verify with `kronos doctor` — paired user count should be ≥ 1.

## Security
- Never echo the bot token in chat.
- Only paired allowlisted users may interact with the agent.
