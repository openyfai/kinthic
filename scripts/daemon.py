from __future__ import annotations

import multiprocessing
import os
import signal
import sys
import time
from pathlib import Path

from aria.utils.logger import setup_logger

log = setup_logger("aria.daemon")


def run_web_worker() -> None:
    """Entry point for the Web API Process."""
    try:
        from scripts import cli
        cli.run_web()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Web worker crashed: {e}")
        sys.exit(1)


def run_telegram_worker() -> None:
    """Entry point for the Telegram Bot Process."""
    try:
        from scripts import cli
        cli.run_telegram()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Telegram worker crashed: {e}")
        sys.exit(1)


import asyncio

async def _worker_loop():
    from aria.storage.database import Database
    from aria.utils.config import DB_PATH
    from aria.core.cognitive_loop import CognitiveLoop

    db = Database(str(DB_PATH))
    await db.connect()

    goal_row = None
    log.info("Cognitive worker spawned. Polling for pending goals...")
    while True:
        goal_row = await db.fetch_one("SELECT * FROM goals WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1")
        if goal_row:
            break
        await asyncio.sleep(5.0)

    log.info(f"Picked up pending goal: {goal_row['id']}")
    
    # Claim the goal to prevent other instances from grabbing it
    await db.execute("UPDATE goals SET status = 'active' WHERE id = ?", (goal_row['id'],))
    await db.close() # Close lightweight connection

    # Spin up the Heavy Cognitive Brain
    loop = CognitiveLoop()
    await loop.startup()
    try:
        # Inject the goal as a system command
        await loop.process_turn(f"[SYSTEM TASK - EXECUTE GOAL]: {goal_row['description']}")
    finally:
        await loop.shutdown()
        
    log.info("Task completed. Ephemeral Cognitive Worker is committing seppuku to free RAM.")
    sys.exit(0)

def run_cognitive_worker() -> None:
    """Entry point for the Ephemeral Cognitive Worker."""
    try:
        asyncio.run(_worker_loop())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Cognitive worker crashed: {e}")
        sys.exit(1)


class DaemonWatchdog:
    """The multi-process supervisor."""

    def __init__(self):
        self.web_process: multiprocessing.Process | None = None
        self.telegram_process: multiprocessing.Process | None = None
        self.cognitive_process: multiprocessing.Process | None = None
        self.running = False

    def start_process(self, target, name: str) -> multiprocessing.Process:
        log.info(f"Watchdog starting {name}...")
        p = multiprocessing.Process(target=target, name=name, daemon=True)
        p.start()
        return p

    def run(self) -> None:
        self.running = True

        # Handle SIGTERM for graceful shutdown
        def handle_sigterm(*args):
            log.info("Watchdog received SIGTERM. Shutting down...")
            self.running = False

        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

        log.info("--- ARIA V3 Watchdog Started ---")

        # Start initial processes
        self.web_process = self.start_process(run_web_worker, "WebWorker")
        self.telegram_process = self.start_process(run_telegram_worker, "TelegramWorker")
        self.cognitive_process = self.start_process(run_cognitive_worker, "CognitiveWorker")

        # The Watchdog Loop
        while self.running:
            try:
                # 1. Check Web Worker
                if self.web_process and not self.web_process.is_alive():
                    log.warning("Web worker died! Watchdog restarting it...")
                    self.web_process = self.start_process(run_web_worker, "WebWorker")

                # 2. Check Telegram Worker
                if self.telegram_process and not self.telegram_process.is_alive():
                    log.warning("Telegram worker died! Watchdog restarting it...")
                    self.telegram_process = self.start_process(run_telegram_worker, "TelegramWorker")

                # 3. Check Cognitive Worker
                if self.cognitive_process and not self.cognitive_process.is_alive():
                    log.warning("Cognitive worker died! Watchdog restarting it...")
                    self.cognitive_process = self.start_process(run_cognitive_worker, "CognitiveWorker")

                time.sleep(2.0)  # Gentle polling
            except Exception as e:
                log.error(f"Watchdog error: {e}")
                time.sleep(5.0)

        # Shutdown sequence
        log.info("Terminating all child processes...")
        if self.web_process: self.web_process.terminate()
        if self.telegram_process: self.telegram_process.terminate()
        if self.cognitive_process: self.cognitive_process.terminate()
        log.info("Watchdog shutdown complete.")


def main() -> None:
    # multiprocessing on Windows requires spawn, which is default for Py3.8+ on Win
    watchdog = DaemonWatchdog()
    watchdog.run()

if __name__ == "__main__":
    main()
