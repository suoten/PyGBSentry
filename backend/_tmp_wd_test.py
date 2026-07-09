import asyncio
from app.sip.watchdog import (
    start_watchdog, cancel_watchdog,
    start_stream_switch_watchdog, cancel_stream_switch_watchdog,
    watchdog_stats, cancel_all_watchdogs,
)

print("import OK")

fired = {"async": False, "sync": False, "sswitch": False, "cancelled": False}

async def async_on_timeout():
    await asyncio.sleep(0.01)
    fired["async"] = True

def sync_returning_coro():
    async def _inner():
        await asyncio.sleep(0.01)
        fired["sswitch"] = True
    return _inner()

def cancelled_cb():
    fired["cancelled"] = True  # should NOT fire

async def t():
    # 1. async watchdog fires
    start_watchdog(key="invite:call-1", timeout_seconds=0.1, on_timeout=async_on_timeout)
    await asyncio.sleep(0.3)
    print("after async fire:", fired, "stats:", watchdog_stats())

    # 2. cancelled watchdog does NOT fire
    start_watchdog(key="invite:call-2", timeout_seconds=0.1, on_timeout=cancelled_cb)
    cancel_watchdog("invite:call-2")
    await asyncio.sleep(0.2)
    print("after cancel:", fired, "stats:", watchdog_stats())

    # 3. stream-switch watchdog with sync-lambda-returning-coroutine fires
    start_stream_switch_watchdog(call_id="call-3", timeout_seconds=0.1, on_timeout=sync_returning_coro)
    await asyncio.sleep(0.3)
    print("after stream_switch fire:", fired, "stats:", watchdog_stats())

    # 4. cancel_stream_switch_watchdog
    start_stream_switch_watchdog(call_id="call-4", timeout_seconds=0.1, on_timeout=cancelled_cb)
    cancel_stream_switch_watchdog("call-4")
    await asyncio.sleep(0.2)
    print("after ss cancel:", fired, "stats:", watchdog_stats())

    cancel_all_watchdogs()

asyncio.run(t())
print("DONE", fired)
