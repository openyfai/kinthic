import asyncio
import time
import sys

from silex.llm.base import retry_on_transient, get_circuit_breaker, CircuitBreakerTripped, CircuitBreakerState

class MockProvider:
    provider_name = "anthropic"

    @retry_on_transient(max_retries=2, base_delay=0.1)
    async def failing_call(self):
        # Simulate 502 Bad Gateway
        raise Exception("502 Bad Gateway")
        
    @retry_on_transient(max_retries=2, base_delay=0.1)
    async def successful_call(self):
        return "OK"

async def main():
    print("[CHAOS TEST] Triggering Anthropic 502 Fault Simulation...")
    provider = MockProvider()
    
    # Configure the global circuit breaker for tests to be very aggressive
    cb = get_circuit_breaker("anthropic")
    cb.max_failures = 3
    cb.cooldown_seconds = 2.0
    
    # 1. Trigger failures until breaker trips
    for i in range(3):
        try:
            await provider.failing_call()
        except Exception as e:
            if isinstance(e, CircuitBreakerTripped):
                print(f"-> Attempt {i+1} raised CircuitBreakerTripped as expected.")
            else:
                print(f"-> Attempt {i+1} raised generic exception (Retries exhausted).")

    # The breaker should now be OPEN.
    if cb.state != CircuitBreakerState.OPEN:
        print("[CHAOS TEST] FAILED. Circuit Breaker did not transition to OPEN.")
        sys.exit(1)
        
    # 2. Assert fast-fail when OPEN
    print("-> Verifying instant fast-fail when OPEN...")
    start_time = time.time()
    try:
        await provider.failing_call()
    except CircuitBreakerTripped:
        pass
    except Exception as e:
        print(f"[CHAOS TEST] FAILED. Expected CircuitBreakerTripped but got: {e}")
        sys.exit(1)
        
    duration = time.time() - start_time
    if duration > 0.05:
        print(f"[CHAOS TEST] FAILED. Fast-fail took too long: {duration}s. Network is still blocking.")
        sys.exit(1)
        
    print(f"-> Fast-fail succeeded in {duration:.4f}s.")
    
    # 3. Assert cooldown / HALF-OPEN
    print(f"-> Waiting for cooldown ({cb.cooldown_seconds}s)...")
    await asyncio.sleep(cb.cooldown_seconds + 0.1)
    
    print("-> Verifying probe request...")
    res = await provider.successful_call()
    if res != "OK":
        print("[CHAOS TEST] FAILED. Probe request did not return OK.")
        sys.exit(1)
        
    if cb.state != CircuitBreakerState.CLOSED:
        print(f"[CHAOS TEST] FAILED. Circuit Breaker did not RESET to CLOSED. State is {cb.state}")
        sys.exit(1)
        
    print("[CHAOS TEST] SUCCESS. Circuit Breaker successfully tripped, fast-failed, cooled down, and reset.")

if __name__ == "__main__":
    asyncio.run(main())
