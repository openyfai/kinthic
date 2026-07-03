import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Callable, Coroutine

logger = logging.getLogger("SILEX.SagaOrchestrator")

class SagaContext:
    def __init__(self):
        self.saga_id: uuid.UUID = uuid.uuid4()
        self.payload: Dict[str, Any] = {}
        self.execution_logs: List[str] = []

    @property
    def transaction_id(self) -> uuid.UUID:
        return self.saga_id

class SagaStep:
    def __init__(self, name: str,
                 action: Callable[[SagaContext], Coroutine[Any, Any, None]],
                 compensate: Callable[[SagaContext], Coroutine[Any, Any, None]],
                 is_pivot: bool = False,
                 depends_on: List[str] = None):
        self.name = name
        self.action = action # Forward async operation
        self.compensate = compensate # Idempotent compensating operation
        self.is_pivot = is_pivot # Irreversibility flag
        self.depends_on = depends_on or []

class AutonomousSagaOrchestrator:
    def __init__(self, db_engine_ref: Any):
        self.db = db_engine_ref
        self.registered_steps: List[SagaStep] = []

    async def _safe_telemetry_write(self, query: str, params: tuple):
        try:
            await self.db.execute(query, params)
        except Exception as e:
            logger.error(f"Non-fatal telemetry write failure: {e}")

    def register_step(self, name: str,
                      action: Callable[[SagaContext], Coroutine[Any, Any, None]],
                      compensate: Callable[[SagaContext], Coroutine[Any, Any, None]],
                      is_pivot: bool = False,
                      depends_on: List[str] = None):
        """Registers a Saga step containing forward and compensating actions."""
        self.registered_steps.append(SagaStep(name, action, compensate, is_pivot, depends_on))
        logger.info(f"Step '{name}' registered (Pivot: {is_pivot}, Depends: {depends_on}).")

    async def execute(self, context: SagaContext) -> bool:
        """Executes the forward Saga workflow using a DAG parallel topological sort, running compensating rollbacks on failure."""
        completed_steps: List[SagaStep] = []
        pivot_passed = False
        failed_exception = None

        await self._safe_telemetry_write(
            "INSERT INTO saga_telemetry_logs (saga_id, status, current_step, created_at) VALUES (?,?,?,?);",
            (str(context.saga_id), "STARTED", "INITIALIZATION", datetime.now(timezone.utc).isoformat())
        )

        events = {step.name: asyncio.Event() for step in self.registered_steps}

        async def run_step(step: SagaStep):
            nonlocal pivot_passed, failed_exception
            
            # Wait for dependencies to complete
            for dep in step.depends_on:
                if dep in events:
                    await events[dep].wait()
                if failed_exception:
                    return  # Fast-fail if a sibling crashed

            logger.info(f"Executing forward step: {step.name}")
            await self._safe_telemetry_write(
                "UPDATE saga_telemetry_logs SET status =?, current_step =? WHERE saga_id =?;",
                ("PENDING", step.name, str(context.saga_id))
            )

            if step.is_pivot:
                pivot_passed = True
                await self._safe_telemetry_write(
                    "UPDATE saga_telemetry_logs SET status =? WHERE saga_id =?;",
                    ("PIVOT_REACHED", str(context.saga_id))
                )

            try:
                await step.action(context)
                completed_steps.append(step)
                context.execution_logs.append(f"SUCCESS: {step.name}")

                await self._safe_telemetry_write(
                    "UPDATE saga_telemetry_logs SET current_step =?, status =? WHERE saga_id =?;",
                    (step.name, "STEP_COMPLETED", str(context.saga_id))
                )
                events[step.name].set()
            except Exception as ex:
                logger.error(f"Unrecoverable execution fault at step '{step.name}': {str(ex)}")

                if pivot_passed:
                    logger.critical(f"Fault occurred post-pivot at step '{step.name}'. Rollback impossible. Escalating forward retry policies.")
                    retry_success = await self._forward_retry(step, context)
                    if retry_success:
                        completed_steps.append(step)
                        context.execution_logs.append(f"SUCCESS (RECOVERED): {step.name}")
                        await self._safe_telemetry_write(
                            "UPDATE saga_telemetry_logs SET current_step =?, status =? WHERE saga_id =?;",
                            (step.name, "STEP_COMPLETED", str(context.saga_id))
                        )
                        events[step.name].set()
                        return
                    else:
                        await self._escalate_post_pivot_failure(step, context, ex)
                        
                if not failed_exception:
                    failed_exception = ex
                for e in events.values():
                    e.set()
                raise ex

        try:
            async with asyncio.TaskGroup() as tg:
                for step in self.registered_steps:
                    tg.create_task(run_step(step))
        except Exception:
            pass # TaskGroup raises ExceptionGroup on failure; we capture specific failures in failed_exception

        if failed_exception:
            if not pivot_passed:
                await self._rollback_compensable_steps(completed_steps, context)
                return False
            else:
                raise failed_exception

        await self._safe_telemetry_write(
            "UPDATE saga_telemetry_logs SET status =? WHERE saga_id =?;",
            ("COMPLETED_SUCCESSFULLY", str(context.saga_id))
        )
        return True

    async def _forward_retry(self, step: SagaStep, context: SagaContext) -> bool:
        """
        Attempts forward recovery of a failed post-pivot step using exponential backoff.
        Returns True if successful, False if retries are exhausted.
        """
        max_retries = 3
        backoff_factor = 2.0
        initial_delay = 0.1 # short delay for tests and responsive recovery
        
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            logger.info(f"Attempting forward retry #{attempt} for post-pivot step '{step.name}' in {delay:.2f}s...")
            await asyncio.sleep(delay)
            try:
                await step.action(context)
                logger.info(f"Forward retry #{attempt} for step '{step.name}' succeeded!")
                return True
            except Exception as ex:
                logger.warning(f"Forward retry #{attempt} for step '{step.name}' failed: {ex}")
                delay *= backoff_factor
                
        return False

    async def _rollback_compensable_steps(self, completed_steps: List[SagaStep], context: SagaContext):
        """Executes compensating transactions in LIFO order to achieve non-linear rollback."""
        logger.warning(f"Initiating Saga rollback sequence. Compensations to execute: {len(completed_steps)}")

        await self._safe_telemetry_write(
            "UPDATE saga_telemetry_logs SET status =? WHERE saga_id =?;",
            ("ROLLING_BACK", str(context.saga_id))
        )

        for step in reversed(completed_steps):
            logger.warning(f"Reverting step '{step.name}' via compensating action: {step.compensate.__name__}")
            try:
                await step.compensate(context)
                await self._safe_telemetry_write(
                    "INSERT INTO saga_telemetry_logs (saga_id, status, current_step, created_at) VALUES (?,?,?,?);",
                    (str(context.saga_id), "COMPENSATED", step.name, datetime.now(timezone.utc).isoformat())
                )
            except Exception as comp_ex:
                logger.critical(f"FATAL: Compensating action for step '{step.name}' failed: {str(comp_ex)}")
                await self._safe_telemetry_write(
                    "UPDATE saga_telemetry_logs SET status =? WHERE saga_id =?;",
                    ("COMPENSATION_FAILED", str(context.saga_id))
                )
                raise comp_ex

        logger.info("Rollback complete. System state successfully restored.")
        await self._safe_telemetry_write(
            "UPDATE saga_telemetry_logs SET status =? WHERE saga_id =?;",
            ("ROLLED_BACK", str(context.saga_id))
        )

    async def _escalate_post_pivot_failure(self, step: SagaStep, context: SagaContext, ex: Exception):
        """Handles post-pivot failures, writing crash diagnostics to disk for manual intervention."""
        from silex.utils.config import WORKSPACE_DIR
        import os
        logger.critical(f"CRITICAL FAULT: Post-pivot failure at step '{step.name}' in Saga '{context.saga_id}'. Exception: {ex}")
        await self._safe_telemetry_write(
            "UPDATE saga_telemetry_logs SET status =?, current_step =? WHERE saga_id =?;",
            ("CRITICAL_POST_PIVOT_FAILURE", step.name, str(context.saga_id))
        )

        diagnostics = (
            f"========================================\n"
            f"SAGA CRASH DIAGNOSTICS ({datetime.now(timezone.utc).isoformat()})\n"
            f"========================================\n"
            f"Saga ID: {context.saga_id}\n"
            f"Failed Step: {step.name}\n"
            f"Exception: {type(ex).__name__}: {ex}\n"
            f"Payload: {context.payload}\n"
            f"Execution Logs:\n" + "\n".join(f"  - {log}" for log in context.execution_logs) + "\n"
            "========================================\n\n"
        )
        try:
            # Phase 4 Fix: Move disk operations inside try/except to prevent OSError loops
            log_dir = os.path.join(str(WORKSPACE_DIR), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "saga_faults.log")
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(diagnostics)
            logger.info(f"Crash diagnostics written to {log_path}")
        except Exception as write_err:
            logger.error(f"Failed to write crash diagnostics to disk: {write_err}")
