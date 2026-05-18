from __future__ import annotations

import multiprocessing
import os
import signal
import sys
import time
import asyncio

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
        error_str = str(e).lower()
        if "unauthorized" in error_str or "invalid token" in error_str:
            log.error("Telegram bot token is invalid or revoked. Telegram integration disabled.")
            sys.exit(0) # Exit with code 0 so the Watchdog knows NOT to restart it
        log.error(f"Telegram worker crashed: {e}")
        sys.exit(1)

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
    
    # Initialize Heartbeat table
    await db.execute("CREATE TABLE IF NOT EXISTS heartbeats (process TEXT PRIMARY KEY, last_seen TEXT)")

    # Background Heartbeat Task
    async def heartbeat_loop():
        try:
            while True:
                await db.execute("INSERT OR REPLACE INTO heartbeats (process, last_seen) VALUES (?, ?)", ("cognitive_worker", str(time.time())))
                await asyncio.sleep(60.0)
        except asyncio.CancelledError:
            pass

    hb_task = asyncio.create_task(heartbeat_loop())
    
    # Spin up the Heavy Cognitive Brain
    loop = CognitiveLoop()
    await loop.startup(target_query=goal_row['description'])
    try:
        # Inject the goal as a system command
        await loop.process_turn(f"[SYSTEM TASK - EXECUTE GOAL]: {goal_row['description']}")
    finally:
        hb_task.cancel()
        await loop.shutdown()
        await db.close()
        
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

def run_watcher_worker() -> None:
    """Entry point for the Debounced FS Watcher."""
    try:
        from aria.storage.database import Database
        from aria.utils.config import DB_PATH
        from aria.knowledge_graph.watcher import DebouncedWatcher
        
        async def _run():
            db = Database(str(DB_PATH))
            await db.connect()
            watcher = DebouncedWatcher(db)
            await watcher.run_loop()
            
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception:
        sys.exit(1)


def run_cron_worker() -> None:
    """Entry point for the Background Cron Worker (Issues 11 and 14)."""
    try:
        import asyncio
        from aria.storage.database import Database
        from aria.utils.config import DB_PATH
        
        async def _run():
            db = Database(str(DB_PATH))
            await db.connect()
            while True:
                try:
                    # Issue 11: Graph Pruning
                    await db.execute("DELETE FROM knowledge_nodes WHERE last_validated < datetime('now', '-30 days') AND confidence < 0.5")
                    
                    # Issue 14: Job Queue TTL
                    await db.execute("DELETE FROM goals WHERE status IN ('completed', 'failed') AND updated_at < datetime('now', '-7 days')")
                    
                    log.info("Cron worker finished weekly consolidation pass.")
                except Exception as e:
                    log.error(f"Cron worker error: {e}")
                
                # Sleep for 24 hours
                await asyncio.sleep(86400)
                
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Cron worker crashed: {e}")
        sys.exit(1)


class DaemonWatchdog:
    """The multi-process supervisor."""

    def __init__(self):
        self.web_process: multiprocessing.Process | None = None
        self.telegram_process: multiprocessing.Process | None = None
        self.cognitive_process: multiprocessing.Process | None = None
        self.watcher_process: multiprocessing.Process | None = None
        self.cron_process: multiprocessing.Process | None = None
        self.running = False

    def start_process(self, target, name: str) -> multiprocessing.Process:
        log.info(f"Watchdog starting {name}...")
        p = multiprocessing.Process(target=target, name=name, daemon=True)
        p.start()
        return p

    def _recover_stale_jobs(self) -> None:
        """Resets active jobs back to pending to recover from an unclean shutdown."""
        import asyncio
        from aria.storage.database import Database
        from aria.utils.config import DB_PATH
        
        async def _run():
            db = Database(str(DB_PATH))
            await db.connect()
            stale_jobs = await db.fetch_all("SELECT id, description FROM goals WHERE status = 'active'")
            for job in stale_jobs:
                log.warning(f"Recovered stale active job after unclean shutdown: {job['id']}")
                await db.execute("UPDATE goals SET status = 'pending', completion_notes = 'Recovered after unclean shutdown' WHERE id = ?", (job['id'],))
            if stale_jobs:
                log.info(f"Successfully recovered {len(stale_jobs)} orphaned jobs to pending queue.")
            await db.close()
            
        try:
            asyncio.run(_run())
        except Exception as e:
            log.error(f"Failed to run recovery cleanup: {e}")

    def _check_heartbeats(self) -> None:
        """Issue 6: Checks if the Cognitive Worker has frozen for > 3 hours."""
        import asyncio
        from aria.storage.database import Database
        from aria.utils.config import DB_PATH
        
        async def _run():
            db = Database(str(DB_PATH))
            await db.connect()
            await db.execute("CREATE TABLE IF NOT EXISTS heartbeats (process TEXT PRIMARY KEY, last_seen TEXT)")
            hb_row = await db.fetch_one("SELECT last_seen FROM heartbeats WHERE process = 'cognitive_worker'")
            if hb_row:
                last_seen = float(hb_row["last_seen"])
                if time.time() - last_seen > 3 * 3600: # 3 hours
                    if self.cognitive_process and self.cognitive_process.is_alive():
                        log.error("VYN cognitive worker was stuck and has been restarted.")
                        self.cognitive_process.kill()
            await db.close()
            
        try:
            asyncio.run(_run())
        except Exception:
            pass

    def run(self) -> None:
        self.running = True

        # Handle SIGTERM for graceful shutdown
        def handle_sigterm(*args):
            log.info("Watchdog received SIGTERM. Shutting down...")
            self.running = False

        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

        log.info("--- VYN V3 Watchdog Started ---")
        
        # Issue 2: Recover orphaned jobs before workers can grab them
        self._recover_stale_jobs()

        # Start initial processes
        self.web_process = self.start_process(run_web_worker, "WebWorker")
        self.telegram_process = self.start_process(run_telegram_worker, "TelegramWorker")
        self.cognitive_process = self.start_process(run_cognitive_worker, "CognitiveWorker")
        self.watcher_process = self.start_process(run_watcher_worker, "WatcherWorker")
        self.cron_process = self.start_process(run_cron_worker, "CronWorker")

        # The Watchdog Loop
        while self.running:
            try:
                # 1. Check Web Worker
                if self.web_process and not self.web_process.is_alive():
                    log.warning("Web worker died! Watchdog restarting it...")
                    self.web_process = self.start_process(run_web_worker, "WebWorker")

                # 2. Check Telegram Worker
                if self.telegram_process and not self.telegram_process.is_alive():
                    if self.telegram_process.exitcode == 0:
                        self.telegram_process = None # Clean disable, do not restart
                    else:
                        log.warning("Telegram worker died! Watchdog restarting it...")
                        self.telegram_process = self.start_process(run_telegram_worker, "TelegramWorker")

                # 3. Check Cognitive Worker
                if self.cognitive_process and not self.cognitive_process.is_alive():
                    log.warning("Cognitive worker died! Watchdog restarting it...")
                    self.cognitive_process = self.start_process(run_cognitive_worker, "CognitiveWorker")
                else:
                    self._check_heartbeats()

                # 4. Check Watcher Worker
                if self.watcher_process and not self.watcher_process.is_alive():
                    log.warning("Watcher worker died! Watchdog restarting it...")
                    self.watcher_process = self.start_process(run_watcher_worker, "WatcherWorker")

                # 5. Check Cron Worker
                if self.cron_process and not self.cron_process.is_alive():
                    log.warning("Cron worker died! Watchdog restarting it...")
                    self.cron_process = self.start_process(run_cron_worker, "CronWorker")

                time.sleep(2.0)  # Gentle polling
            except Exception as e:
                log.error(f"Watchdog error: {e}")
                time.sleep(5.0)

        # Shutdown sequence
        log.info("Terminating all child processes gracefully...")
        processes = [p for p in (self.web_process, self.telegram_process, self.cognitive_process, self.watcher_process, self.cron_process) if p]
        
        for p in processes:
            if p.is_alive():
                # Send SIGTERM for graceful exit
                os.kill(p.pid, signal.SIGTERM)
                
        # Wait up to 10 seconds for them to shut down cleanly
        timeout = 10
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            if all(not p.is_alive() for p in processes):
                break
            time.sleep(0.5)
            
        # Hard kill any survivors
        for p in processes:
            if p.is_alive():
                log.warning(f"Process {p.name} (PID {p.pid}) did not shut down in time. Sending SIGKILL.")
                try:
                    p.kill() # Python 3.7+ equivalent of SIGKILL
                except Exception:
                    pass
        log.info("Watchdog shutdown complete.")


def main() -> None:
    # multiprocessing on Windows requires spawn, which is default for Py3.8+ on Win
    watchdog = DaemonWatchdog()
    watchdog.run()

if __name__ == "__main__":
    main()
