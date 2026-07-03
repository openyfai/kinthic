# Kronos Support Playbook

Having issues with Kronos? Before opening an issue in Discord or GitHub, please review this playbook for common solutions.

## Issue 1: Telegram Pairing Fails
**Symptom:** You type the 1-time PIN into the Telegram bot, but nothing happens or the bot ignores you.
**Cause:** Unpaired users have a strict rate limit of 5 messages per minute to prevent brute-forcing. If you spammed the bot before getting the code, you might be temporarily soft-blocked.
**Solution:**
1. Wait 60 seconds without sending any messages to the bot.
2. In your terminal, stop the daemon (`Ctrl+C`).
3. Run `kronos telegram run` again to generate a new pairing PIN.
4. Send only the exact PIN to the bot.

## Issue 2: Tool Approval Timeout / Hanging
**Symptom:** You are waiting for Kronos to reply, but it seems to have frozen after you asked it to write a file or run a command.
**Cause:** The agent has hit an `/approve` checkpoint, but you missed the notification, or the Telegram UI didn't render the Inline Keyboard.
**Solution:**
1. Check your terminal output. If the terminal shows `[PENDING APPROVAL]`, type `approve` directly into the terminal and hit Enter.
2. In Telegram, you can always manually type `/approve` to unstick the pipeline, even if the button is missing.

## Issue 3: Token Cost Surprise
**Symptom:** Your LLM provider bill is higher than expected.
**Cause:** Long-running sessions with complex graphs can cause the context window to inflate, despite our compression efforts.
**Solution:**
1. Run `kronos usage` in the terminal (or `/usage` in Telegram) to see a breakdown of costs per model.
2. If you are using expensive frontier models (like Claude 3.5 Sonnet or GPT-4o) for basic chat, ensure the `SmartRouter` is enabled so it can offload simple queries to cheaper models (like Haiku or Flash). Check `/status` to confirm the Fast Path is configured.
3. If a session gets too long, tell the agent: "Summarize our progress, finish the current goal, and I will start a new session." This resets the token window.

## General Debugging
If you encounter random errors, run:
```bash
kronos doctor
```
This command checks your network, API keys, provider settings, and security flags for risky combinations. Include its output if you open a GitHub issue.
