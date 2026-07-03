# Kinthic Demo Video Script

**Target Length:** 3 Minutes
**Goal:** Show the ease of installation, Telegram pairing, and the `/approve` loop.

## Scene 1: The One-Line Install
**Visual:** A clean macOS/Ubuntu terminal.
**Action:**
1. User runs `curl -fsSL https://kinthic.openyf.dev/install.sh | bash`
2. Fast-forward through dependency installation (uv fetching packages).
3. Success message: "Kinthic installed. Run `kinthic onboard` to begin."

## Scene 2: Onboarding & Pairing
**Visual:** Terminal on the left, Telegram Desktop on the right.
**Action:**
1. User types `kinthic onboard`.
2. Selects "Anthropic" and pastes an API key.
3. Selects "Telegram" as the interface and pastes a Bot Token.
4. The terminal displays a pairing code: `Pairing Code: 8492-4912`
5. User switches to Telegram, opens the bot, and types `/pair 8492-4912`.
6. Bot replies: "✅ Device paired successfully! You are now the operator."
7. Terminal says "Daemon starting..."

## Scene 3: The `/approve` Flow
**Visual:** Full screen Telegram.
**Action:**
1. User sends: "Write a python script that prints hello world and save it to `hello.py`"
2. Bot replies: "I've drafted the script. Requesting permission to write to `hello.py`."
3. An Inline Keyboard appears with "✅ Approve" and "❌ Reject".
4. User clicks "Approve".
5. Bot replies: "Saved to `hello.py`!"

## Scene 4: Conclusion
**Visual:** Split screen, Telegram and the generated `hello.py` file.
**Voiceover/Text:** "Kinthic. The open-source cognitive agent that respects your boundaries. Try it today."
