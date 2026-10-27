"""Wait for queue drainage with an explicit deadline."""

import sys
from pathlib import Path

from valkey import Valkey

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.append(str(_src))

from base.backfill import wait_for_capacity
from valkey_settings import ValkeySettings


def wait_queue(
    poll_interval: float = 6,
    silent: bool = False,
    until_length: int = 0,
    timeout: float = 300,
    vk=None,
):
    """Wait at most ``timeout`` seconds; reuse an optional caller-owned client."""
    owned = vk is None
    if owned:
        settings = ValkeySettings()
        vk = Valkey(
            host=settings.host,
            port=settings.port,
            socket_timeout=30,
            socket_connect_timeout=30,
        )
    try:

        def report(total):
            if not silent:
                print(
                    f"Remaining: {total:5d} Errors: {vk.llen('process-errors')}"
                )

        wait_for_capacity(
            vk,
            max_queue_length=max(0, until_length),
            timeout=timeout,
            poll_interval=poll_interval,
            on_poll=report,
        )
    finally:
        if owned:
            vk.close()


if __name__ == "__main__":
    import fire

    fire.Fire(wait_queue)
